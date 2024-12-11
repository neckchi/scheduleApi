import asyncio
import hashlib
import logging
import uuid
from datetime import timedelta
from typing import Dict, Optional, Union, Any

import orjson
from redis.asyncio import BlockingConnectionPool, Redis, WatchError
from starlette.responses import JSONResponse

from app.internal.setting import Settings, load_yaml


class ClientSideCache:
    def __init__(self):
        setting: Settings = Settings()
        self.__pool: BlockingConnectionPool = BlockingConnectionPool(
            host=setting.redis_host.get_secret_value(),
            port=setting.redis_port.get_secret_value(),
            db=setting.redis_db.get_secret_value(),
            username=setting.redis_user.get_secret_value() if setting.redis_user.get_secret_value() != 'None' else None,
            password=setting.redis_pw.get_secret_value() if setting.redis_pw.get_secret_value() != 'None' else None
        )
        self.port_mapping_cache: Dict[str, str] = {}

    def __await__(self):
        return self.initialize_database().__await__()

    def generate_uuid_from_string(self, namespace: str, key: Union[str, Any]) -> str:
        key: str = str(key) if not isinstance(key, str) else key
        namespace_uuid: uuid.UUID = uuid.UUID(bytes=hashlib.md5(namespace.encode('utf-8')).digest())
        return str(uuid.uuid5(namespace_uuid, key))

    async def initialize_database(self) -> 'ClientSideCache':
        retries: int = 2
        while retries > 0:
            try:
                self._pool: Redis = await Redis(connection_pool=self.__pool)
                await self._pool.ping()
                logging.info(f'Connected To Redis - {self._pool.connection_pool}', extra={'custom_attribute': None})
                return self
            except Exception as disconnect:
                retries -= 1
                if retries == 0:
                    raise ConnectionError('Unable to connect to RedisDB after retries')
                else:
                    await asyncio.sleep(3)
                    logging.critical(f'Retry - Unable to connect to the RedisDB - {disconnect}', extra={'custom_attribute': None})

    async def set(self, key: str, value: JSONResponse,
                  expire: int = timedelta(hours=load_yaml()['data']['backgroundTasks']['scheduleExpiry']),
                  namespace: Optional[str] = 'data') -> None:
        hashKey: str = self.generate_uuid_from_string(namespace=namespace, key=key)
        async with self._pool.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(hashKey)
                pipe.multi()
                redis_set: Optional[bool] = pipe.set(name=hashKey, value=orjson.dumps(value), ex=expire, nx=True)
                if redis_set is None:
                    await pipe.discard()
                    logging.info(f'Key:{hashKey} already exists')
                else:
                    await pipe.execute()
                    logging.info(f'Background Task:Cached {namespace} into schedule collection - {hashKey}')
            except WatchError as watch_error:
                logging.error(watch_error)
            except Exception as insert_db:
                logging.error(insert_db)

    async def get(self, key: str, namespace: Optional[str] = 'data') -> Optional[Dict[str, Any]]:
        hashKey: str = self.generate_uuid_from_string(namespace=namespace, key=key)
        retries: int = 3
        while retries > 0:
            try:
                logging.info(f'Background Task:Getting {namespace} from Redis - {hashKey}')
                get_result: Optional[bytes] = await self._pool.get(hashKey)
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

    async def close(self) -> None:
        await self.__pool.disconnect()
        await self.__pool.aclose()
