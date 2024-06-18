from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml,log_queue_listener
from fastapi import status,HTTPException,BackgroundTasks,Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError,ResponseValidationError
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from uuid import UUID,uuid4
from typing import Literal,Generator,Callable
from datetime import timedelta
import httpx
import logging
import orjson
import asyncio
import atexit


QUEUE_LISTENER = log_queue_listener()
async def startup_event():
    QUEUE_LISTENER.start()
    await db.initialize_database()
    # Global Client Setup
    global httpx_client
    httpx_client = HTTPXClientWrapper()
    logging.info("HTTPX Client initialized")

async def shutdown_event():
    atexit.register(httpx_client.aclose)
    atexit.register(QUEUE_LISTENER.stop)
    logging.info("HTTPX Client closed")


"""Given that each of the 7000 employees performs 7000 searches per hour, this amounts to 7000×7000=49,000,000
7000×7000=49,000,000 searches per hour. To break it down per second:49,000,000searches / 3600 seconds ≈ 13,611 searches per second

However, this doesn't mean we need 13,611 connections simultaneously because these searches will be distributed over time and can reuse TCP connections and keep-alive.

If we estimate that each search takes around 1 second, and considering we need to handle 13,611 searches per second, you'd start with a similar number for max connections. 
However, given that not all searches will happen exactly at the same time and some connections can be reused, we can reduce this number.

A good starting point is to use around 10-20% of the peak searches per second as concurrent connections.
Therefor,  10% of 13,611 is approximately 1361 connections.
We can adjust this number based on the actual performance and server capacity.
Since KN employees are performing searches frequently (every hour), setting a higher keep-alive expiry can help reuse connections effectively."""


SSL_CONTEXT = httpx.create_ssl_context()
# KN_PROXY:httpx.Proxy = httpx.Proxy("http://zscaler.proxy.int.kn:80")
KN_PROXY:httpx.Proxy = httpx.Proxy("http://proxy.eu-central-1.aws.int.kn:80")
HTTPX_TIMEOUT = httpx.Timeout(load_yaml()['data']['connectionPoolSetting']['elswhereTimeOut'], connect=load_yaml()['data']['connectionPoolSetting']['connectTimeOut'])
HTTPX_LIMITS = httpx.Limits(max_connections=load_yaml()['data']['connectionPoolSetting']['maxClientConnection'],
                            max_keepalive_connections=load_yaml()['data']['connectionPoolSetting']['maxKeepAliveConnection'],keepalive_expiry=load_yaml()['data']['connectionPoolSetting']['keepAliveExpiry'])
HTTPX_ASYNC_HTTP = httpx.AsyncHTTPTransport(retries=3,proxy=KN_PROXY,verify=SSL_CONTEXT,limits=HTTPX_LIMITS)
class HTTPXClientWrapper(httpx.AsyncClient):
    __slots__ = ('session_id')
    def __init__(self):
        super().__init__(timeout=HTTPX_TIMEOUT, transport=HTTPX_ASYNC_HTTP)
        self.session_id: str = str(uuid4())

#Individual Client Session Setup
    # @classmethod
    # async def get_httpx_client_wrapper(cls) -> Generator:
    #     async with cls() as standalone_client:
    #         logging.info(f'Client Session Started - {standalone_client.session_id}')
    #         try:
    #             yield standalone_client
    #         except (ConnectionError,httpx.ConnectTimeout,httpx.ConnectError) as connect_error:
    #             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,detail=f'{connect_error.__class__.__name__}:{connect_error}')
    #         except ValueError as value_error:
    #             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{value_error.__class__.__name__}:{value_error}')
    #         except RequestValidationError as request_error:
    #             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f'{request_error.__class__.__name__}:{request_error}')
    #         except ResponseValidationError as response_error:
    #             raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{response_error.__class__.__name__}:{response_error}')
    #         except Exception as eg:
    #             logging.error(f'{eg.__class__.__name__}:{eg.args}')
    #             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f'An error occurred while creating the client - {eg.args}')
    #         logging.info(f'Client Session Closed - {standalone_client.session_id}')


    async def parse(self,url: str, method: str = Literal['GET', 'POST'],params: dict = None, headers: dict = None, json: dict = None, token_key=None,data: dict = None,
                    background_tasks: BackgroundTasks = None, expire=timedelta(hours = load_yaml()['data']['backgroundTasks']['scheduleExpiry']),stream: bool = False):
        """Fetch the file from carrier API and deserialize the json file """
        if not stream:
            response = await self.request(method=method, url=url, params=params, headers=headers, json=json,data=data)
            if response.status_code == status.HTTP_206_PARTIAL_CONTENT: #only CMA returns 206 if the number of schedule is more than 49. That means we shouldnt deserialize the json response at the beginning coz there are more responses need to be fetched based on the header range.
                yield response
            if response.status_code == status.HTTP_200_OK:
                response_json = response.json()
                if background_tasks:
                    background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire)
                yield response_json
            if response.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR,status.HTTP_502_BAD_GATEWAY):
                logging.critical(f'Unable to connect to {url}')
                yield None
            else:yield None
        else:
            """
            At the moment Only Maersk need consumer to stream the response
            """
            client_request = self.build_request(method=method, url=url, params=params, headers=headers, data=data)
            stream_request = await self.send(client_request, stream=True)
            if stream_request.status_code == status.HTTP_200_OK:
                result = StreamingResponse(stream_request.aiter_lines(),status_code=status.HTTP_200_OK, background=BackgroundTask(stream_request.aclose))
                async for data in result.body_iterator:
                    response = orjson.loads(data)
                    if background_tasks:
                        background_tasks.add_task(db.set, key=token_key, value=response, expire=expire)
                    yield response
            else:yield None


    def gen_all_valid_schedules(self,response:Response,matrix:Generator,product_id:UUID,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:bool):
        """Validate the schedule and serialize hte json file excluding the field without any value """
        flat_list:Generator = (item for row in matrix if not isinstance(row, Exception) and row is not None for item in row)
        sorted_schedules:list = sorted(flat_list, key=lambda tt: (tt['etd'], tt['transitTime']))
        count_schedules:int = len(sorted_schedules)
        if count_schedules == 0:
            headers:dict = {"X-Correlation-ID":str(product_id),"Pragma":"no-cache","Cache-Control":  "no-cache, no-store, max-age=0, must-revalidate"}
            final_result = JSONResponse(headers=headers,status_code=status.HTTP_200_OK,content=jsonable_encoder(schema_response.Error(id=product_id,detail=f"{point_from}-{point_to} schedule not found")))
        else:
            final_result = schema_response.Product(
            productid=product_id,
            origin=point_from,
            destination=point_to, noofSchedule=count_schedules,
            schedules=sorted_schedules).model_dump(mode='json',exclude_none=True)
            response.headers["X-Correlation-ID"] = str(product_id)
            response.headers["Pragma"] = "no-cache"
            response.headers["Cache-Control"] = "private, max-age=7200"
            if not task_exception:
                background_tasks.add_task(db.set,key=product_id,value=final_result)
        return final_result

#Global Client Setup
async def get_httpx_client_wrapper() -> Generator[HTTPXClientWrapper, None, None]:
    """Global ClientConnection Pool  Setup"""
    try:
        yield httpx_client
    except (ConnectionError, httpx.ConnectTimeout, httpx.ConnectError) as connect_error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f'{connect_error.__class__.__name__}:{connect_error}')
    except ValueError as value_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'{value_error.__class__.__name__}:{value_error}')
    except RequestValidationError as request_error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f'{request_error.__class__.__name__}:{request_error}')
    except ResponseValidationError as response_error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f'{response_error.__class__.__name__}:{response_error}')
    except Exception as eg:
        logging.error(f'{eg.__class__.__name__}:{eg.args}')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f'An error occurred while creating the client - {eg.args}')

class AsyncTaskManager:
    """Currently there is no built in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled
    From BU perspective, all those carrier schedules are independent from one antoher so we shouldnt let a failed task to cancel all other successful tasks"""
    def __init__(self,default_timeout=load_yaml()['data']['connectionPoolSetting']['asyncDefaultTimeOut'],max_retries=load_yaml()['data']['connectionPoolSetting']['retryNumber']):
        self.__tasks:dict = dict()
        self.error:bool = False
        self.default_timeout:int = default_timeout
        self.max_retries:int = max_retries
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type = None, exc = None, tb= None):
        self.results = await asyncio.gather(*self.__tasks.values(), return_exceptions=True)

    async def _timeout_wrapper(self, coro:Callable, task_name:str):
        """Wrap a coroutine with a timeout and retry logic."""
        retries:int = 0
        adjusted_timeout = self.default_timeout
        while retries < self.max_retries:
            try:
                return await asyncio.wait_for(coro(), timeout=self.default_timeout)
            except (asyncio.TimeoutError,asyncio.CancelledError,httpx.ReadTimeout,httpx.ReadError,httpx.ConnectTimeout,):
                """Due to timeout, the coroutine task is cancelled. Once its cancelled, we retry it 3 times"""
                logging.error(f"{task_name} timed out after {self.default_timeout} seconds. Retrying {retries + 1}/{self.max_retries}...")
                retries += 1
                adjusted_timeout += 3
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries. the schedule  wont be cached anything")
        self.error = True
        # return coro()
        return None

    def create_task(self, name:str,coro:Callable):
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro,task_name=name))

    def results(self) -> Generator:
        return (result for result in self.results if not isinstance(result, Exception)) if self.error else self.results