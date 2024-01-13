from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml
from fastapi import status,HTTPException,BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from uuid import UUID,uuid4
from typing import Literal,Generator
import httpx
import logging
import orjson
import asyncio

class AsyncTaskManager:
    """Currently there is no built in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled e.g:timeout
    From my perspective, all those carrier schedules are independent from one antoher so we shouldnt let one/more failed task to cancel all other successful tasks"""
    def __init__(self,default_timeout=5):
        self.__tasks:dict = dict()
        self.error:list[dict] #Once this becomes true, we wont do any caching.vice versa
        self.default_timeout = default_timeout

    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type = None, exc = None, tb= None):
        if exc_type is not None:
            logging.error(f'Exception occurred:: {exc_type} - {exc}')

        results = await asyncio.gather(*self.__tasks.values(), return_exceptions=True)
        task_names:list = list(self.__tasks.keys())
        self.error:list[dict] = [{task_names[i]: result} for i, result in enumerate(results) if isinstance(result, Exception)]
        if self.error != []:
            for error in self.error:
                task_name, exception = list(error.items())[0]
                logging.critical(f"{task_name} connection attempts failed:{exception}")
            results:list = [result for result in results if not isinstance(result, Exception)]
        return results

    async def _timeout_wrapper(self, coro:asyncio.Task, task_name):
        """Wrap a coroutine with a timeout.Even though the task is timeout, it will still proceed with the remaining tasks"""
        try:
            return await asyncio.wait_for(asyncio.shield(coro), timeout=self.default_timeout)
        except asyncio.TimeoutError:
            logging.error(f"{task_name}  timed out after {self.default_timeout} seconds")
            return await coro
    def create_task(self,carrier, coro):
        self.__tasks[carrier] = asyncio.create_task(self._timeout_wrapper(coro=coro,task_name=carrier))



class HTTPXClientWrapper():
    def __init__(self):
        self.session_id: str = str(uuid4())
        self.client:httpx.AsyncClient = httpx.AsyncClient(proxies="http://zscaler.proxy.int.kn:80", verify=False, timeout=httpx.Timeout(30.0, connect=65.0), limits=httpx.Limits(max_connections=None))
        logging.info(f'Client Session Started - {self.session_id}')

    async def close(self):
        logging.info(f'Client Session Closed - {self.session_id}')
        await self.client.aclose()

    @staticmethod
    async def get_httpx_client_wrapper() -> Generator:
        wrapper = HTTPXClientWrapper()
        try:
            yield wrapper
        except ConnectionError as connect_error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail=f'{connect_error.__class__.__name__}:{connect_error}')
        except ValueError as value_error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,detail=f'{value_error.__class__.__name__}:{value_error}')
        except Exception as eg:
            logging.error(f'{eg.__class__.__name__}:{eg.args}')
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,detail=f'An error occurred while creating the client - {eg.args}')
        finally:
            await wrapper.close()


    async def parse(self,url: str, method: str = Literal['GET', 'POST'],params: dict = None, headers: dict = None, json: dict = None, token_key=None,
                          data: dict = None, background_tasks: BackgroundTasks = None, expire=None,stream: bool = False):
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
            At the moment Only Maersk('MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI') need consumer to stream the response
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


    def gen_all_valid_schedules(self,matrix:list,product_id:UUID,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:list):
        flat_list: list = []
        for row in matrix:
            if row is not None:
                flat_list.extend(row)
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
            background_tasks.add_task(db.set, value=final_result) if not task_exception else ...  # for MongoDB
            if not task_exception:
                if load_yaml()['data']['backgroundTasks']['cacheDB'] == 'Redis':
                    background_tasks.add_task(db.set,key=product_id,value=final_result)
                else: background_tasks.add_task(db.set, value=final_result)
        return final_result



