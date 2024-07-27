from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml,log_queue_listener
from fastapi import status,HTTPException,BackgroundTasks,Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from typing import Literal,Generator,Callable,AsyncGenerator,Dict,Any
from threading import Lock
from uuid import UUID
from datetime import timedelta
import httpx
import logging
import orjson
import asyncio
import time

class HTTPXClientWrapper():
    def __init__(self):
        self.default_limits = load_yaml()['data']['connectionPoolSetting']
        self.limits = self.default_limits.copy()
        self.lock = Lock()
        self._initialize_client()
    def _initialize_client(self):
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(self.limits['elswhereTimeOut'],pool=self.limits['poolTimeOut'],connect=self.limits['connectTimeOut']),
                                        limits=httpx.Limits(max_connections=self.limits['maxClientConnection'],max_keepalive_connections=self.limits['maxKeepAliveConnection'],keepalive_expiry=self.limits['keepAliveExpiry']),
                                        verify=False,proxy = httpx.Proxy("http://proxy.eu-central-1.aws.int.kn:80"))
                                        # verify = False)
    async def _adjust_pool_limits(self):
        """designed to dynamically adjust the connection pool limits of the httpx client when a PoolTimeout error occurs"""
        with self.lock:
            self.limits['maxClientConnection'] += 20
            self.limits['maxKeepAliveConnection'] += 10
            self.client._transport._pool._max_connections = self.limits['maxClientConnection']
            self.client._transport._pool._max_keepalive_connections = self.limits['maxKeepAliveConnection']

    async def close(self):
        await self.client.aclose()

    # Individual Client Session Setup
    @classmethod
    async def get_individual_httpx_client_wrapper(cls) -> Generator:
        async with cls() as standalone_client:
            try:
                yield standalone_client
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
            finally:
                await standalone_client.aclose()
    async def parse(self, scac:str, url: str, method: Literal['GET', 'POST'] = 'GET', params: dict = None, headers: dict = None,json: dict = None, token_key: str|UUID = None, data: dict = None,
                    background_tasks: BackgroundTasks = None,expire: timedelta = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),stream: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch the file from carrier API and deserialize the json file """
        if not stream:
            async for response in self.handle_standard_response(scac,url, method, params, headers, json, data, token_key,background_tasks, expire):
                yield response
        else:
            async for response in self.handle_streaming_response(scac,url, method, params, headers, data, token_key,background_tasks, expire):
                yield response

    async def handle_standard_response(self,scac:str, url: str, method: str, params: dict, headers: dict, json: dict, data: dict, token_key: str, background_tasks: BackgroundTasks,
                                       expire: timedelta) -> AsyncGenerator[Dict[str,Any],None]:
        try:
            response = await self.client.request(method=method, url=url, params=params, headers=headers, json=json, data=data)
            logging.info(f'{method} {scac} took {response.elapsed.total_seconds()}s to process the request {response.url} {response.http_version} {response.status_code} {response.reason_phrase}')
            if response.status_code == status.HTTP_206_PARTIAL_CONTENT:
                yield response
            elif response.status_code == status.HTTP_200_OK:
                response_json = response.json()
                if background_tasks:
                    background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire,log_component=f'{scac} token')
                yield response_json
            elif response.status_code in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_502_BAD_GATEWAY):
                logging.critical(f'Unable to connect to {response.url}')
                yield None
            else:
                yield None
        except httpx.PoolTimeout as e:
            logging.info(f'PoolTimeout : Increasing pool size...')
            await self._adjust_pool_limits()
            yield None
    async def handle_streaming_response(self,scac:str, url: str, method: str, params: dict, headers: dict, data: dict,token_key: str, background_tasks: BackgroundTasks,
                                        expire: timedelta) -> AsyncGenerator[Dict[str, Any],None]:
        try:
            async with self.client.stream(method, url, params=params, headers=headers, data=data) as stream_request:
                if stream_request.status_code == status.HTTP_200_OK:
                    async for data in stream_request.aiter_lines():
                        response = orjson.loads(data)
                        logging.info(f'{method} {scac} took {stream_request.elapsed.total_seconds()}s to process the request {stream_request.url} {stream_request.http_version} {stream_request.status_code} {stream_request.reason_phrase}')
                        if background_tasks:
                            background_tasks.add_task(db.set, key=token_key, value=response, expire=expire, log_component=f'{scac} location code')
                        yield response
                else:
                    yield None
        except httpx.PoolTimeout as e:
            logging.info(f'PoolTimeout occurred:Increasing pool size...')
            await self._adjust_pool_limits()
            yield None

    def gen_all_valid_schedules(self,correlation:str|None,response:Response,product_id:UUID,matrix:Generator,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:bool):
        """Validate the schedule and serialize hte json file excluding the field without any value """
        mapping_time = time.time()
        flat_list:list = [item for row in matrix if not isinstance(row, Exception) and row is not None for item in row]
        logging.info(f'mapping_time = {time.time() - mapping_time:.2f}s Gathering all the schedule files obtained from carriers and mapping to our data format')
        count_schedules:int = len(flat_list)
        response.headers.update({"X-Correlation-ID": str(correlation), "Cache-Control": "public, max-age=7200" if count_schedules >0 else "no-cache, no-store, max-age=0, must-revalidate",
                                 "KN-Count-Schedules": str(count_schedules)})

        if count_schedules == 0:
            final_result = JSONResponse(status_code=status.HTTP_200_OK,content=jsonable_encoder(schema_response.Error(productid=product_id,details=f"{point_from}-{point_to} schedule not found")))
        else:
            validation_start_time = time.time()
            sorted_schedules: list = sorted(flat_list, key=lambda tt: (tt['etd'], tt['transitTime']))
            final_set:dict = {'productid':product_id,'origin':point_from,'destination':point_to, 'noofSchedule':count_schedules,'schedules':sorted_schedules}
            final_validation = schema_response.PRODUCT_ADAPTER.validate_python(final_set)
            logging.info(f'validation_time={time.time() - validation_start_time:.2f}s Validated the schedule ')

            dump_start_time = time.time()
            final_result = schema_response.PRODUCT_ADAPTER.dump_python(final_validation,mode='json',exclude_none=True)
            logging.info(f'serialization_time={time.time() - dump_start_time:.2f}s Generate schedule file and exclude all the fields which are equal to None')
            if not task_exception:
                background_tasks.add_task(db.set,key=product_id,value=final_result,log_component='the whole schedules')
        """
        HTTP connection pooling status 
        IDLE:The connection is not currently being used for any request.It is available for reuse by new requests.
        ACTIVE:The connection is currently being used to handle an HTTP request.It is not available for other requests until the current request completes.
        CLOSED:The connection has been terminated.It is no longer part of the connection pool and cannot be reused.
        ACQUIRED:The connection has been taken from the pool but is not yet actively processing a request.It might be in the process of setting up or awaiting the next action."""
        background_tasks.add_task(lambda : logging.info(self.client._transport._pool._pool))
        return final_result


logging.getLogger("httpx").setLevel(logging.WARNING)
httpx_client = HTTPXClientWrapper()
queue_listener = log_queue_listener()
async def startup_event():
    queue_listener.start()
    await db.initialize_database()
    logging.info("HTTPX Client initialized",extra={'custom_attribute':None})

async def shutdown_event():
    queue_listener.stop()
    await db.close()
    await httpx_client.close()
    logging.info("HTTPX Client closed", extra={'custom_attribute': None})


async def get_global_httpx_client_wrapper() -> HTTPXClientWrapper:
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
class AsyncTaskManager():
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
        if exc_type:
            for task in self.__tasks.values():
                if not task.done():
                    logging.info('Cancel remaining tasks if an exception occurred')
                    task.cancel()
            await asyncio.gather(*self.__tasks.values(), return_exceptions=True)
        return not exc_type
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
                adjusted_timeout += 2
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries. the schedule  wont be cached anything")
        self.error = True
        # return coro()
        return None

    def create_task(self, name:str,coro:Callable):
        logging.info(f'Forward the request to {name.split("_task")[0]}')
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro,task_name=name))

    def results(self) -> Generator:
        return (result for result in self.results if not isinstance(result, Exception)) if self.error else self.results