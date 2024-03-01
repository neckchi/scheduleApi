from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml
from fastapi import status,HTTPException,BackgroundTasks
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

#
class AsyncTaskManager:
    """Currently there is no built in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled
    From BU perspective, all those carrier schedules are independent from one antoher so we shouldnt let a failed task to cancel all other successful tasks"""
    def __init__(self,default_timeout=25,max_retries=3):
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
            except asyncio.TimeoutError:
                """Due to timeout, the coroutine task is cancelled. Once its cancelled, we retry it 3 times"""
                logging.error(f"{task_name} timed out after {self.default_timeout} seconds. Retrying {retries + 1}/{self.max_retries}...")
                retries += 1
                adjusted_timeout += 3
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries.")
        # return coro()
        return None

    def create_task(self, name:str,coro:Callable):
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro,task_name=name))

    def results(self) -> list:
        task_names = list(self.__tasks.keys())
        for i, result in enumerate(self.results):
            if isinstance(result, Exception):
                task_name = task_names[i]
                logging.critical(f"{task_name} connection attempts failed: {result}")
                self.error = True
        return [result for result in self.results if not isinstance(result, Exception)] if self.error else self.results



class HTTPXClientWrapper():
    def __init__(self):
        self.session_id: str = str(uuid4())
        self.client:httpx.AsyncClient = httpx.AsyncClient(proxies="http://zscaler.proxy.int.kn:80", verify=False, timeout=httpx.Timeout(30.0, connect=65.0), limits=httpx.Limits(max_connections=200,max_keepalive_connections=20))
        logging.info(f'Client Session Started - {self.session_id}')

    async def close(self):
        logging.info(f'Client Session Closed - {self.session_id}')
        await self.client.aclose()

    @staticmethod
    async def get_httpx_client_wrapper() -> Generator:
        standalone_client = HTTPXClientWrapper() ## standalone client session
        try:
            yield standalone_client
        except ConnectionError as connect_error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f'{connect_error.__class__.__name__}:{connect_error}')
        except ValueError as value_error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{value_error.__class__.__name__}:{value_error}')
        except RequestValidationError as request_error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f'{request_error.__class__.__name__}:{request_error}')
        except ResponseValidationError as response_error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{response_error.__class__.__name__}:{response_error}')
        except Exception as eg:
            logging.error(f'{eg.__class__.__name__}:{eg.args}')
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f'An error occurred while creating the client - {eg.args}')
        finally:
            await standalone_client.close()


    async def parse(self,url: str, method: str = Literal['GET', 'POST'],params: dict = None, headers: dict = None, json: dict = None, token_key=None,
                          data: dict = None, background_tasks: BackgroundTasks = None, expire=timedelta(hours = load_yaml()['data']['backgroundTasks']['scheduleExpiry']),stream: bool = False):
        if not stream:
            response = await self.client.request(method=method, url=url, params=params, headers=headers, json=json,data=data)
            if response.status_code == 206: #only CMA returns 206 if the number of schedule is more than 49. That means we shouldnt deserialize the json response at the beginning coz there are more responses need to be fetched based on the header range.
                yield response
            if response.status_code == 200:
                response_json = response.json()
                if background_tasks:
                    background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire)
                yield response_json
            if response.status_code in (500,502):
                logging.critical(f'Unable to connect to {url}')
                yield None
            else:yield None
        else:
            """
            At the moment Only Maersk need consumer to stream the response
            """
            client_request = self.client.build_request(method=method, url=url, params=params, headers=headers, data=data)
            stream_request = await self.client.send(client_request, stream=True)
            if stream_request.status_code == 200:
                result = StreamingResponse(stream_request.aiter_lines(),status_code=200, background=BackgroundTask(stream_request.aclose))
                async for data in result.body_iterator:
                    response = orjson.loads(data)
                    if background_tasks:
                        background_tasks.add_task(db.set, key=token_key, value=response, expire=expire)
                    yield response
            else:yield None


    def gen_all_valid_schedules(self,matrix:list,product_id:UUID,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:bool):
        flat_list:list = [item for row in matrix if row is not None for item in row]
        sorted_schedules:list = sorted(flat_list, key=lambda tt: (tt['etd'][:10], tt['transitTime']))
        count_schedules:int = len(sorted_schedules)
        if count_schedules == 0:
            final_result = JSONResponse(status_code=status.HTTP_404_NOT_FOUND,content=jsonable_encoder(schema_response.Error(id=product_id,detail=f"{point_from}-{point_to} schedule not found")))
        else:
            final_result = schema_response.Product(
            productid=product_id,
            origin=point_from,
            destination=point_to, noofSchedule=count_schedules,
            schedules=sorted_schedules).model_dump(exclude_none=True)
            if not task_exception:
                if load_yaml()['data']['backgroundTasks']['cacheDB'] == 'Redis':
                    background_tasks.add_task(db.set,key=product_id,value=final_result)
                else: background_tasks.add_task(db.set, value=final_result)
        return final_result



