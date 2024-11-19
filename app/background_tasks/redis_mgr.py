from datetime import timedelta
from redis.asyncio import BlockingConnectionPool, Redis, WatchError
from app.config import Settings, load_yaml
from starlette.responses import JSONResponse
from uuid import uuid5, NAMESPACE_DNS
from typing import Optional
import uuid
import logging
import orjson
import asyncio


class ClientSideCache:
    def __init__(self):
        setting = Settings()
        self.__pool = BlockingConnectionPool(host=setting.redis_host.get_secret_value(),
                                             port=setting.redis_port.get_secret_value(),
                                             db=setting.redis_db.get_secret_value(),
                                             username=setting.redis_user.get_secret_value() if setting.redis_user.get_secret_value() != 'None' else None,
                                             password=setting.redis_pw.get_secret_value() if setting.redis_pw.get_secret_value() != 'None' else None)

    def __await__(self):
        return self.initialize_database().__await__()

    def generate_cache_key(self, key: Optional[uuid.UUID] = None, original_response: Optional[bool] = False,
                           scac: Optional[str] = None, params: Optional[str] = None):
        if original_response:
            return uuid5(NAMESPACE_DNS, f'{scac}-original-response-{params}')
        else:
            return key

    async def initialize_database(self):
        retries: int = 2
        while retries > 0:
            try:
                self._pool = await Redis(connection_pool=self.__pool)
                await self._pool.ping()
                logging.info(f'Connected To Redis - {self._pool.connection_pool}', extra={'custom_attribute': None})
                return self
            except Exception as disconnect:
                retries -= 1
                if retries == 0:
                    raise ConnectionError('Unable to connect to RedisDB after retries')
                else:
                    await asyncio.sleep(3)
                    logging.critical(f'Retry - Unable to connect to the RedisDB - {disconnect}',
                                     extra={'custom_attribute': None})

    async def set(self, value: JSONResponse,
                  expire: int = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),
                  key: Optional[uuid.UUID] = None, original_response: Optional[bool] = False,
                  scac: Optional[str] = None, params: Optional[str] = None, log_component: Optional[str] = 'data'):
        generate_key = self.generate_cache_key(key=key, scac=scac, params=params, original_response=original_response)
        async with self._pool.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(
                    generate_key.urn)  # tells Redis to monitor this key. If this key is modified by any other client before the transaction is executed, the transaction will be aborted.
                pipe.multi()  # puts the pipeline back into buffered mode. Commands issued after this point are queued up and will be executed atomically.
                redis_set = pipe.set(name=generate_key.urn, value=orjson.dumps(value), ex=expire,
                                     nx=True)  # Using nx = True to make sure the record doesnt exist and prevent us from overwriting the original record
                if redis_set is None:
                    await pipe.discard()  # Flush all previously queued commands in a transaction and restores the connection state to normal
                    logging.info(f'Key:{generate_key} already exists')
                else:
                    await pipe.execute()
                    logging.info(f'Background Task:Cached {log_component} into schedule collection - {generate_key}')
            except WatchError as watch_error:
                logging.error(
                    watch_error)  # FIFO so we wont do anything as we only need the first entry to be taken if any other client is going to change the same key
            except Exception as insert_db:
                logging.error(insert_db)

    async def get(self, key: Optional[uuid.UUID] = None, original_response: Optional[bool] = False,
                  scac: Optional[str] = None, params: Optional[str] = None, log_component: Optional[str] = 'data'):
        generate_key = self.generate_cache_key(key=key, scac=scac, params=params, original_response=original_response)
        retries: int = 3
        while retries > 0:
            try:
                logging.info(f'Background Task:Getting {log_component} from Redis - {generate_key}')
                get_result = await self._pool.get(generate_key.urn)
                if get_result:
                    return orjson.loads(get_result)
                return None
            except Exception as find_error:
                retries -= 1
                if retries == 0:
                    raise ConnectionError('Unable to connect to RedisDB and retrieve cache from Redis')
                else:
                    logging.critical(f'Unable to retrieve cache from RedisDB due to {find_error}')
                    await self.initialize_database()

    async def close(self):
        await self.__pool.disconnect()
        await self.__pool.aclose()
