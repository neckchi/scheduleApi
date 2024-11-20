from app.background_tasks import db
from app.schemas import schema_response
from app.config import load_yaml, log_queue_listener
from fastapi import status, HTTPException, BackgroundTasks, Response
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from typing import Generator, Callable, AsyncGenerator, Dict, Any, Optional, Union
from uuid import UUID
from datetime import timedelta
from itertools import chain
import aiohttp
import logging
import orjson
import asyncio
import time
import ssl


class HTTPClientWrapper:
    def __init__(self, proxy: Optional[str] = None) -> None:
        self.default_limits = load_yaml()['data']['connectionPoolSetting']
        self.limits = self.default_limits.copy()
        self.proxy = proxy
        self.lock = asyncio.Lock()
        self._client: Optional[aiohttp.ClientSession] = None
        self._queue_listener = log_queue_listener()

    async def startup(self) -> None:
        """Initialize the HTTP client and start necessary services."""
        self._queue_listener.start()
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
                trust_env=False,
                headers={"Connection": "Keep-Alive"},
                skip_auto_headers=['User-Agent']
            )
            logging.info("Aiohttp Client initialized", extra={'custom_attribute': None})

    async def shutdown(self) -> None:
        """Shut down the HTTP client and stop necessary services."""
        self._queue_listener.stop()
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
            except (aiohttp.ClientConnectionError) as connect_error:
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

    async def parse(self, scac: str, url: str, method: str = 'GET', params: Optional[Dict[str, Any]] = None,
                    headers: Optional[Dict[str, Any]] = None,
                    json: Optional[Dict[str, Any]] = None, token_key: Optional[Union[str, UUID]] = None,
                    data: Optional[Dict[str, Any]] = None,
                    background_tasks: Optional[BackgroundTasks] = None,
                    expire: timedelta = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),
                    stream: bool = False) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch the file from carrier API and deserialize the json file """
        if not stream:
            async for response in self.handle_standard_response(scac, url, method, params, headers, json, data, token_key, background_tasks, expire):
                yield response
        else:
            async for response in self.handle_streaming_response(scac, url, method, params, headers, data, token_key, background_tasks, expire):
                yield response

    async def handle_standard_response(self, scac: str, url: str, method: str, params: Optional[Dict[str, Any]],
                                       headers: Optional[Dict[str, Any]],
                                       json: Optional[Dict[str, Any]], data: Optional[Dict[str, Any]],
                                       token_key: Optional[Union[str, UUID]],
                                       background_tasks: Optional[BackgroundTasks], expire: timedelta) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            start_time = time.time()
            async with self._client.request(method=method, url=url, params=params, headers=headers, json=json, data=data, proxy=self.proxy) as response:
                response_time = time.time() - start_time
                logging.info(f'{method} {scac} took {response_time:.2f}s to process the request {response.url} {response.status}')
                # self.carrier_response_time = time.time() - start_time
                # logging.info(f'{method} {scac} took {self.carrier_response_time:.2f}s to process the request {response.url} {response.status}')
                if response.status == status.HTTP_206_PARTIAL_CONTENT:
                    yield response
                elif response.status == status.HTTP_200_OK:
                    response_json = await response.json()
                    if background_tasks:
                        background_tasks.add_task(db.set, key=token_key, value=response_json, expire=expire, log_component=f'{scac} token')
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
        # except aiohttp.ConnectionTimeoutError as e:
        #     logging.info(f'ConnectionError:{e}.Increasing pool size.')
        #     await self._adjust_pool_limits()
        #     yield None

    async def handle_streaming_response(self, scac: str, url: str, method: str, params: Optional[Dict[str, Any]],
                                        headers: Optional[Dict[str, Any]],
                                        data: Optional[Dict[str, Any]], token_key: Optional[Union[str, UUID]],
                                        background_tasks: Optional[BackgroundTasks],
                                        expire: timedelta) -> AsyncGenerator[Dict[str, Any], None]:
        try:
            start_time = time.time()
            async with self._client.request(method, url=url, params=params, headers=headers, data=data, proxy=self.proxy) as stream_request:
                # logging.info(self.client._connector._conns)
                response_time = time.time() - start_time
                logging.info(f'{method} {scac} took {response_time:.2f}s to process the request {stream_request.url} {stream_request.status}')
                if stream_request.status == status.HTTP_200_OK:
                    async for data in stream_request.content:
                        response = orjson.loads(data)
                        if background_tasks:
                            background_tasks.add_task(db.set, key=token_key, value=response, expire=expire, log_component=f'{scac} location code')
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

    def gen_all_valid_schedules(self, correlation: Optional[str], response: Response, product_id: UUID,
                                matrix: Generator, point_from: str, point_to: str,
                                background_tasks: BackgroundTasks, task_exception: bool) -> Dict[str, Any]:
        """Validate the schedule and serialize hte json file excluding the field without any value """
        mapping_time = time.time()
        # flat_list:list = [item for row in matrix if not isinstance(row, Exception) and row is not None for item in row]
        flat_list: list = list(chain.from_iterable(row for row in matrix if not isinstance(row, Exception) and row is not None))
        logging.info(f'mapping_time = {time.time() - mapping_time:.2f}s Gathering all the schedule files obtained from carriers and mapping to our data format')
        count_schedules: int = len(flat_list)
        response.headers.update({"X-Correlation-ID": str(correlation), "Connection": "Keep-Alive", "Cache-Control": "max-age=7200,stale-while-revalidate=86400", "KN-Count-Schedules": str(count_schedules)})
        # response.headers.update({"X-Correlation-ID": str(correlation), "Cache-Control": "public, max-age=7200" if count_schedules >0 else "no-cache, no-store, max-age=0, must-revalidate",
        #                          "KN-Count-Schedules": str(count_schedules),"Carrier-Response-Time":str(self.carrier_response_time)})
        if count_schedules == 0:
            final_result = JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(schema_response.Error(productid=product_id, details=f"{point_from}-{point_to} schedule not found")))
        else:
            validation_start_time = time.time()
            sorted_schedules: list = sorted(flat_list, key=lambda schedule: (schedule.etd, schedule.transitTime))
            final_set: dict = {'productid': product_id, 'origin': point_from, 'destination': point_to, 'noofSchedule': count_schedules, 'schedules': sorted_schedules}
            final_validation = schema_response.PRODUCT_ADAPTER.validate_python(final_set)
            logging.info(f'validation_time={time.time() - validation_start_time:.2f}s Validated the schedule ')

            dump_start_time = time.time()
            final_result = schema_response.PRODUCT_ADAPTER.dump_python(final_validation, mode='json', exclude_none=True)
            logging.info(f'serialization_time={time.time() - dump_start_time:.2f}s Generate schedule file and exclude all the fields which are equal to None')
            if not task_exception:
                background_tasks.add_task(db.set, key=product_id, value=final_result, log_component='the whole schedules')
        """
        HTTP connection pooling status
        IDLE:The connection is not currently being used for any request.It is available for reuse by new requests.
        ACTIVE:The connection is currently being used to handle an HTTP request.It is not available for other requests until the current request completes.
        CLOSED:The connection has been terminated.It is no longer part of the connection pool and cannot be reused.
        ACQUIRED:The connection has been taken from the pool but is not yet actively processing a request.It might be in the process of setting up or awaiting the next action."""
        return final_result


http_client = HTTPClientWrapper('http://zscaler.proxy.int.kn:80')


async def startup_event():
    await http_client.startup()


async def shutdown_event():
    await http_client.shutdown()


async def get_global_http_client_wrapper() -> HTTPClientWrapper:
    """Global ClientConnection Pool Setup"""
    try:
        yield http_client
    except (aiohttp.ClientConnectionError) as connect_error:
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
    """Currently there is no built-in  python class and method that we can prevent it from cancelling all conroutine tasks if one of the tasks is cancelled
    From BU perspective,all those carrier schedules are independent from one antoher so we shouldnt let a failed task to cancel all other successful tasks"""

    def __init__(self, default_timeout=load_yaml()['data']['connectionPoolSetting']['asyncDefaultTimeOut'], max_retries=load_yaml()['data']['connectionPoolSetting']['retryNumber']):
        self.__tasks: Dict[str, asyncio.Task] = dict()
        self.error: bool = False
        self.default_timeout: int = default_timeout
        self.max_retries: int = max_retries

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
            except (asyncio.TimeoutError, asyncio.CancelledError, aiohttp.ClientConnectionError, aiohttp.ServerConnectionError):
                """Due to timeout, the coroutine task is cancelled. Once its cancelled, we retry it"""
                logging.warning(f"{task_name} timed out after {self.default_timeout} seconds. Retrying {retries + 1}/{self.max_retries}...")
                retries += 1
                adjusted_timeout += 2
                await asyncio.sleep(1)  # Wait for 1 sec before the next retry
        logging.error(f"{task_name} reached maximum retries. Nothing will be cached")
        self.error = True
        return None

    def create_task(self, name: str, coro: Callable) -> None:
        logging.info(f'Forward the request to {name.split("_task")[0]}')
        self.__tasks[name] = asyncio.create_task(self._timeout_wrapper(coro=coro, task_name=name))

    def results(self) -> Generator:
        return (result for result in self.results if not isinstance(result, Exception)) if self.error else self.results
