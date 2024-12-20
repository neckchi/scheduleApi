import asyncio
import logging
import ssl
import time
from datetime import timedelta
from itertools import chain
from typing import Any, AsyncGenerator, Callable, Dict, Generator, Optional
from uuid import UUID

import aiohttp
import orjson
from fastapi import BackgroundTasks, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import schema_response
from app.internal.logging import setup_logging
from app.internal.setting import load_yaml
from app.storage import db


class HTTPClientWrapper:
    def __init__(self) -> None:
        self.default_limits = load_yaml()['data']['connectionPoolSetting']
        self.limits = self.default_limits.copy()
        self.lock = asyncio.Lock()
        self._client: Optional[aiohttp.ClientSession] = None

    async def startup(self) -> None:
        """Initialize the HTTP client and start necessary services."""
        setup_logging()
        await db.initialize_database()

        if self._client is None:
            ctx = ssl.create_default_context()
            ctx.set_ciphers('DEFAULT')
            self.conn = aiohttp.TCPConnector(
                ssl=ctx,
                ttl_dns_cache=self.limits['dnsCache'],
                limit_per_host=self.limits['maxConnectionPerHost'],
                limit=self.limits['maxClientConnection'],
                keepalive_timeout=self.limits['keepAliveExpiry']
            )
            self._client = aiohttp.ClientSession(
                connector=self.conn,
                timeout=aiohttp.ClientTimeout(
                    total=self.limits['elswhereTimeOut'],
                    connect=self.limits['poolTimeOut']
                ),
                trust_env=True,  # trust_env=True means read environment variables e.g:HTTP_PROXY,HTTPS_PROXY
                headers={"Connection": "Keep-Alive"},
                skip_auto_headers=['User-Agent']
            )
            logging.info("Aiohttp Client initialized", extra={'custom_attribute': None})

    async def shutdown(self) -> None:
        """Shut down the HTTP client and stop necessary services."""
        await db.close()

        if self._client:
            await self._client.close()
            logging.info("Aiohttp Client closed", extra={'custom_attribute': None})

    async def _adjust_pool_limits(self) -> None:
        """Dynamically adjust the connection pool limits of the aiohttp client when a PoolTimeout error occurs"""
        async with self.lock:
            self.limits['maxClientConnection'] += 20
            self.limits['maxConnectionPerHost'] += 10
            self.conn._limit = self.limits['maxClientConnection']
            self.conn._limit_per_host = self.limits['maxConnectionPerHost']

    async def close(self) -> None:
        await self.shutdown()

    @classmethod
    async def get_individual_http_client_wrapper(cls) -> AsyncGenerator["HTTPClientWrapper", None]:
        async with cls() as standalone_client:
            try:
                yield standalone_client
            except aiohttp.ClientConnectionError as connect_error:
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
                await standalone_client.close()

    async def parse(self, url: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None,
                    headers: Optional[Dict[str, Any]] = None,
                    json: Optional[Dict[str, Any]] = None,
                    data: Optional[Dict[str, Any]] = None,
                    background_tasks: Optional[BackgroundTasks] = None,
                    expire: timedelta = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),
                    namespace: str | None = None,
                    stream: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch the file from carrier API and deserialize the json file """
        if not stream:
            async for response in self.handle_standard_response(url, method, params, headers, json, data,
                                                                background_tasks=background_tasks, expire=expire,
                                                                namespace=namespace):
                yield response
        else:
            async for response in self.handle_streaming_response(url, method, params, headers, data,
                                                                 background_tasks=background_tasks, expire=expire,
                                                                 namespace=namespace):
                yield response

    async def handle_extra_response(self, url: str, method: str, params: Optional[Dict[str, Any]],
                                    headers: Optional[Dict[str, Any]], json: Optional[Dict[str, Any]],
                                    data: Optional[Dict[str, Any]], ) -> AsyncGenerator[Dict[str, Any], None]:
        start_time = time.time()
        async with self._client.request(method=method, url=url, params=params, headers=headers, json=json, data=data) as extra_response:
            response_time = time.time() - start_time
            logging.info(
                f'{method} took {response_time:.2f}s to process the request {extra_response.url} {extra_response.status}')
            if extra_response.status in (
                    status.HTTP_206_PARTIAL_CONTENT, status.HTTP_200_OK) and extra_response is not None:
                response_json = await extra_response.json()
                yield response_json

    async def handle_standard_response(self, url: str, method: str, params: Optional[Dict[str, Any]],
                                       headers: Optional[Dict[str, Any]],
                                       json: Optional[Dict[str, Any]], data: Optional[Dict[str, Any]],
                                       background_tasks: Optional[BackgroundTasks], expire: timedelta,
                                       namespace: str | None = None) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            cache_result = await db.get(key=url + str(params), namespace=namespace) if namespace else None
            if cache_result:
                yield cache_result
            else:
                start_time = time.time()
                async with self._client.request(method=method, url=url, params=params, headers=headers, json=json,
                                                data=data) as response:
                    response_time = time.time() - start_time
                    logging.info(
                        f'{method} took {response_time:.2f}s to process the request {response.url} {response.status}')
                    if response.status == status.HTTP_206_PARTIAL_CONTENT:
                        combined_schedule: list = []
                        combined_schedule.extend(await response.json())
                        page: int = 50
                        last_page: int = int(response.headers['content-range'].partition('/')[2])
                        extra_p2p_task = [asyncio.create_task(anext(
                            self.handle_extra_response(method="GET", url=url, params=params, json=json, data=data,
                                                       headers=dict(headers, **{'range': f'{num}-{49 + num}'})))) for
                                          num in range(page, last_page, page)]
                        extra_p2p_result = await asyncio.gather(*extra_p2p_task)
                        combined_schedule.extend(*extra_p2p_result)
                        if background_tasks:
                            background_tasks.add_task(db.set, key=url + str(params), value=combined_schedule,
                                                      expire=expire, namespace=namespace)
                        yield combined_schedule
                    elif response.status == status.HTTP_200_OK:
                        response_json = await response.json()
                        if background_tasks:
                            background_tasks.add_task(db.set, key=url + str(params), value=response_json, expire=expire,
                                                      namespace=namespace)
                        yield response_json
                    elif response.status in (status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_502_BAD_GATEWAY):
                        logging.critical(f'Unable to connect to {response.url}')
                        yield None
                    elif response.status == status.HTTP_429_TOO_MANY_REQUESTS:
                        logging.critical(f'Too Many Request Sent To {response.url}')
                        yield None
                    else:
                        yield None
        except aiohttp.ClientProxyConnectionError as proxy_issue:
            logging.error(f'Proxy Issue:{proxy_issue}')

    async def handle_streaming_response(self, url: str, method: str, params: Optional[Dict[str, Any]],
                                        headers: Optional[Dict[str, Any]],
                                        data: Optional[Dict[str, Any]],
                                        background_tasks: Optional[BackgroundTasks],
                                        expire: timedelta, namespace: str | None = None) -> AsyncGenerator[
            Dict[str, Any], None]:
        try:
            cache_result = await db.get(key=url + str(params), namespace=namespace) if namespace else None
            if cache_result:
                yield cache_result
            else:
                start_time = time.time()
                async with self._client.request(method, url=url, params=params, headers=headers, data=data) as stream_request:
                    # logging.info(self.client._connector._conns)
                    response_time = time.time() - start_time
                    logging.info(
                        f'{method} took {response_time:.2f}s to process the request {stream_request.url} {stream_request.status}')
                    if stream_request.status == status.HTTP_200_OK:
                        async for data in stream_request.content:
                            response = orjson.loads(data)
                            if background_tasks:
                                background_tasks.add_task(db.set, key=url + str(params), value=response, expire=expire,
                                                          namespace=namespace)
                            yield response
                    elif stream_request.status == status.HTTP_429_TOO_MANY_REQUESTS:
                        logging.critical(f'Too Many Request Sent To {stream_request.url}')
                        yield None
                    else:
                        yield None
        except orjson.JSONDecodeError as e:
            logging.error(f'Error parsing JSON:{e}')
            raise
        except aiohttp.ClientProxyConnectionError as proxy_issue:
            logging.error(f'Proxy Issue:{proxy_issue}')

    def gen_all_valid_schedules(self, request: Request, response: Response, product_id: UUID,
                                matrix: Generator, point_from: str, point_to: str,
                                background_tasks: BackgroundTasks, task_exception: bool,
                                failed_scac: Optional[list] = None) -> Dict[str, Any]:
        """Validate the schedule and serialize hte json file excluding the field without any value """
        mapping_time = time.time()
        flat_list: list = list(
            chain.from_iterable(row for row in matrix if not isinstance(row, Exception) and row is not None))
        logging.info(
            f'mapping_time = {time.time() - mapping_time:.2f}s Gathering all the schedule files obtained from carriers and mapping to our data format')
        count_schedules: int = len(flat_list)
        response.headers.update(
            {"Connection": "Keep-Alive", "Cache-Control": "max-age=7200,stale-while-revalidate=86400",
             "KN-Count-Schedules": str(count_schedules)})

        if count_schedules == 0:
            resp_headers: dict = {'retry-failed': ", ".join(failed_scac)} if failed_scac else None
            final_result = JSONResponse(status_code=status.HTTP_200_OK, headers=resp_headers, content=jsonable_encoder(
                schema_response.Error(productid=product_id, details=f"{point_from}-{point_to} schedule not found")))
        else:
            validation_start_time = time.time()
            sorted_schedules: list = sorted(flat_list, key=lambda schedule: (schedule.etd, schedule.transitTime))
            final_set: dict = {'productid': product_id, 'origin': point_from, 'destination': point_to,
                               'noofSchedule': count_schedules, 'schedules': sorted_schedules}
            final_validation = schema_response.PRODUCT_ADAPTER.validate_python(final_set)
            logging.info(f'validation_time={time.time() - validation_start_time:.2f}s Validated the schedule ')

            dump_start_time = time.time()
            final_result = schema_response.PRODUCT_ADAPTER.dump_python(final_validation, mode='json', exclude_none=True)
            logging.info(
                f'serialization_time={time.time() - dump_start_time:.2f}s Generate schedule file and exclude all the fields which are equal to None')
            if not task_exception:
                background_tasks.add_task(db.set, key=request.url, value=final_result, namespace="schedule product")
            else:
                response.headers['retry-failed'] = ", ".join(failed_scac)
        """
        HTTP connection pooling status
        IDLE:The connection is not currently being used for any request.It is available for reuse by new requests.
        ACTIVE:The connection is currently being used to handle an HTTP request.It is not available for other requests until the current request completes.
        CLOSED:The connection has been terminated.It is no longer part of the connection pool and cannot be reused.
        ACQUIRED:The connection has been taken from the pool but is not yet actively processing a request.It might be in the process of setting up or awaiting the next action."""
        return final_result


http_client = HTTPClientWrapper()


async def startup_event():
    await http_client.startup()


async def shutdown_event():
    await http_client.shutdown()


async def get_global_http_client_wrapper() -> HTTPClientWrapper:
    """Global ClientConnection Pool Setup"""
    try:
        yield http_client
    except aiohttp.ClientConnectionError as connect_error:
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
    """Currently there is no built-in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled
    From BU perspective,all those carrier schedules are independent from one antoher so we shouldnt let a failed task to cancel all other successful tasks"""

    def __init__(self, default_timeout=load_yaml()['data']['connectionPoolSetting']['asyncDefaultTimeOut'],
                 max_retries=load_yaml()['data']['connectionPoolSetting']['retryNumber']):
        self.__tasks: Dict[str, asyncio.Task] = dict()
        self.error: bool = False
        self.default_timeout: int = default_timeout
        self.max_retries: int = max_retries
        self.failed_scac: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type=None, exc=None, tb=None):
        self.results = await asyncio.gather(*self.__tasks.values(), return_exceptions=True)

    async def _timeout_wrapper(self, coro: Callable, task_name: str) -> Optional[Any]:
        """Wrap a coroutine with a timeout and retry logic."""
        retries: int = 0
        adjusted_timeout = self.default_timeout
        while retries < self.max_retries:
            try:
                return await asyncio.wait_for(coro(), timeout=self.default_timeout)
            except (
                    asyncio.TimeoutError, asyncio.CancelledError, aiohttp.ClientConnectionError,
                    aiohttp.ServerConnectionError):
                """Due to timeout, the coroutine task is cancelled. Once its cancelled, we retry it"""
                logging.warning(
                    f"{task_name} timed out after {self.default_timeout} seconds. Retrying {retries + 1}/{self.max_retries}...")
                retries += 1
                adjusted_timeout += 2
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries. Nothing will be cached")
        self.error = True
        self.failed_scac.append(task_name.split("_task")[0])
        return None

    def create_task(self, name: str, coro: Callable) -> None:
        logging.info(f'Forward the request to {name.split("_task")[0]}')
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro, task_name=name))

    def results(self) -> Generator:
        return (result for result in self.results if not isinstance(result, Exception)) if self.error else self.results
