from datetime import timedelta
from redis.asyncio import BlockingConnectionPool, Redis
from app.config import Settings,load_yaml
import uuid
import logging
import orjson
import asyncio
import time

class ClientSideCache:
    def __init__(self):
        setting = Settings()
        self.__pool = BlockingConnectionPool(host=setting.redis_host.get_secret_value(),port=setting.redis_port.get_secret_value(),db = setting.redis_db.get_secret_value(),
                                             username=setting.redis_user.get_secret_value() if setting.redis_user.get_secret_value() !='None' else None,
                                             password=setting.redis_pw.get_secret_value() if setting.redis_pw.get_secret_value() !='None' else None)
    def __await__(self):
        return self.initialize_database().__await__()
    async def initialize_database(self):
        retries: int = 2
        while retries > 0:
            try:
                self._pool = await Redis(connection_pool=self.__pool)
                await self._pool.ping()
                logging.info(f'Connected To Redis - {self._pool.connection_pool}')
                return self
            except Exception as disconnect:
                retries -= 1
                if retries == 0:
                    raise ConnectionError(f'Unable to connect to RedisDB after retries ')
                else:
                    time.sleep(3)
                    logging.critical(f'Retry - Unable to connect to the RedisDB - {disconnect}')

    async def set(self, key:uuid.UUID, value: dict| list,expire:int = timedelta(hours = load_yaml()['data']['backgroundTasks']['scheduleExpiry'])):
        async with self._pool.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key.urn) #tells Redis to monitor the 'KEY'. If this key is modified by another client before the transaction is executed, the transaction will be aborted.
                pipe.multi() # puts the pipeline back into buffered mode. Commands issued after this point are queued up and will be executed atomically.
                redis_set = pipe.set(name=key.urn, value=orjson.dumps(value),ex=expire,nx=True)
                if redis_set is None:
                    await pipe.discard() #Flushes all previously queued commands in a transaction and restores the connection state to normal
                    logging.info(f'Key:{key} already exists')
                else:
                    await pipe.execute()
                    logging.info(f'Background Task:Cached data into schedule collection - {key}')
            except Exception as insert_db:
                logging.error(insert_db)
                pass

    async def get(self, key: uuid.UUID):
        retries:int = 3
        while retries > 0:
            try:
                logging.info(f'Background Task:Getting data from Redis - {key}')
                get_result = await self._pool.get(key.urn)
                if get_result:
                    return orjson.loads(get_result)
                return None
            except Exception as find_error:
                retries -= 1
                if retries == 0:
                    raise ConnectionError(f'Unable to connect to RedisDB and retrieve cache from MongoDB')
                else:
                    logging.critical(f'Unable to retrieve cache from RedisDB due to {find_error}')
                    await self.initialize_database()
