from app.background_tasks import db
from app.schemas import schema_response
from fastapi import status,HTTPException,BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from uuid import UUID
from typing import Literal
import httpx
import logging
import orjson
import asyncio

class AsyncTaskManager:
    """Currently there is no built in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled e.g:timeout
    From my perspective, all those carrier schedules are independent from one antoher so we shouldnt let one/more failed task to cancel all other successful tasks"""
    def __init__(self):
        self.__tasks:dict = dict()
        self.error:list #Once this becomes true, we wont do any caching.vice versa

    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type = None, exc = None, tb= None):
        if exc_type is not None:
            logging.error(f'Exception occurred:: {exc_type} - {exc}')
            # Wait for all tasks to complete and handle exceptions
        results = await asyncio.gather(*self.__tasks.values(), return_exceptions=True)
        task_names:list = list(self.__tasks.keys())
        self.error:list[dict] = [{task_names[i]: result} for i, result in enumerate(results) if isinstance(result, Exception)]
        if self.error != []:
            for error in self.error:
                task_name, exception = list(error.items())[0]
                logging.critical(f"{task_name} connection attempts failed due to {exception}")
                results:list = [result for result in results if not isinstance(result, Exception)]
        return results
    def create_task(self,carrier, coro):
        self.__tasks.update({carrier: asyncio.create_task(coro)})

class HTTPXClientWrapper:
    ##Creating new session for each request but this would probably incur performance overhead issue.
    ##even so it also has its own advantage like fault islation, increased flexibility to each request and avoid concurrency issues.
    @staticmethod
    async def get_client():
        timeout = httpx.Timeout(35.0, connect=65.0)
        limits = httpx.Limits(max_connections=None)

        """
        the reason im doing this is make sure we can yield the client to endpoint before start and explicitly close the
        client when the request is done in order to avoid any concurency issue. When we call get_schedules, then FastAPI framworks will handle dependency injection
        and the context management for it https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/

        FastAPI dependancy injection allows us to use generator functions as dependenacy
        """
        try:
            async with httpx.AsyncClient(proxies="http://zscaler.proxy.int.kn:80",verify=False, timeout=timeout, limits=limits) as client:
                # yield the client to the endpoint function
                logging.info(f'Client Session Started')
                yield client
                logging.info(f'Client Session Closed')
                # close the client when the request is done
        except ValueError as value_error: ## Catch validation error
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'{value_error.__class__.__name__}:{value_error}')
        except Exception as eg:
            logging.error(f'{eg.__class__.__name__}:{eg.args}')
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'An error occured while creating the client - {eg.args}')


    @staticmethod
    async def call_client(client: httpx.AsyncClient, url: str, method: str = Literal['GET', 'POST'],
                          params: dict = None, headers: dict = None, json: dict = None, token_key=None,
                          data: dict = None, background_tasks: BackgroundTasks = None, expire=None,
                          stream: bool = False):
        if not stream:
            response = await client.request(method=method, url=url, params=params, headers=headers, json=json,data=data)
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
            client_request = client.build_request(method=method, url=url, params=params, headers=headers, data=data)
            stream_request = await client.send(client_request, stream=True)
            if stream_request.status_code == 200:
                result = StreamingResponse(stream_request.aiter_lines(),status_code=200, background=BackgroundTask(stream_request.aclose))
                async for data in result.body_iterator:
                    response = orjson.loads(data)
                    if background_tasks:
                        background_tasks.add_task(db.set, key=token_key, value=response, expire=expire)
                    yield response
            else:yield None

    @staticmethod
    def get_all_valid_schedules(matrix:list,product_id:UUID,point_from:str,point_to:str,background_tasks:BackgroundTasks,task_exception:list):
        flat_list: list = []
        for row in matrix:
            if row is not None:
                flat_list.extend(row)
        sorted_schedules = sorted(flat_list, key=lambda tt: (tt['etd'][:10], tt['transitTime']))
        count_schedules = len(sorted_schedules)
        if count_schedules == 0:
            final_result = JSONResponse(status_code=status.HTTP_404_NOT_FOUND,content=jsonable_encoder(schema_response.Error(id=product_id,detail=f"{point_from}-{point_to} schedule not found")))
        else:
            final_result = schema_response.Product(
            productid=product_id,
            origin=point_from,
            destination=point_to, noofSchedule=count_schedules,
            schedules=sorted_schedules).model_dump(exclude_none=True)
            background_tasks.add_task(db.set, value=final_result) if not task_exception else ...  # for MongoDB
            # background_tasks.add_task(db.set,key=product_id,value=data) if not task_group.error else ...#for Redis
        return final_result



