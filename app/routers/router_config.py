from functools import cache
from app import config
from app.background_tasks import db
from fastapi import HTTPException
from fastapi import BackgroundTasks
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from typing import Literal
from asyncio import TaskGroup
import httpx

import logging
import orjson


@cache
def get_settings():
    """
    Reading a file from disk is normally a costly (slow) operation
    so we  want to do it only once and then re-use the same settings object, instead of reading it for each request.
    And this is exactly why we need to use python in built wrapper functions - cache for caching the carrier credential
    """
    return config.Settings()

class HTTPXClientWrapper:
    ##Creating new session for each request but this would probably incur performance overhead issue.
    ##even so it also has its own advantage like fault islation, increased flexibility to each request and avoid concurrency issues.
    @staticmethod
    async def get_client():
        timeout = httpx.Timeout(35.0, connect=60.0)
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
        except ExceptionGroup as eg:
            group_exception:list = [f'Error:{index} - {sub_eg}' for index, sub_eg in enumerate(eg.exceptions,start=1)]
            logging.error(group_exception)
            raise HTTPException(status_code=500, detail=f'An error occured while creating the client - {group_exception}')


    @staticmethod
    async def call_client(client: httpx.AsyncClient, url: str, method: str = Literal['GET', 'POST'],
                          params: dict = None, headers: dict = None, json: dict = None, token_key=None,
                          data: dict = None, background_tasks: BackgroundTasks = None, expire=None,
                          stream: bool = False):
        if not stream:
            response = await client.request(method=method, url=url, params=params, headers=headers, json=json,data=data)
            if response.status_code == 206:
                yield response
            if response.status_code == 200:
                response_json = response.json()
                if background_tasks:
                    background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire)
                yield response_json
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
    def flatten_list(matrix:list) -> list:
        flat_list: list = []
        for row in matrix:
            if row is not None:
                flat_list.extend(row)
            else:
                pass
        return flat_list

class GatheringTaskGroup(TaskGroup):
    def __init__(self):
        super().__init__()
        self.__tasks = []

    def create_task(self, coro, *, name=None, context=None):
        try:
            task = super().create_task(coro, name=name, context=context)
            self.__tasks.append(task)
            return task
        except ExceptionGroup as eg:
            for error in eg.exceptions:
                logging.error(f'TaskGroup error occured:{error}')
                pass
    def results(self):
        return [task.result() for task in self.__tasks]