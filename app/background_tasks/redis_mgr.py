from datetime import timedelta
from redis.asyncio import BlockingConnectionPool, Redis
from app.config import Settings,load_yaml
import uuid
import logging
import orjson
import asyncio

class ClientSideCache:
    def __init__(self):
        setting = Settings()
        self.__pool = BlockingConnectionPool(host=setting.redis_host.get_secret_value(),port=setting.redis_port.get_secret_value(),db = setting.redis_db.get_secret_value(),
                                             username=setting.redis_user.get_secret_value() if setting.redis_user.get_secret_value() !='None' else None,
                                             password=setting.redis_pw.get_secret_value() if setting.redis_pw.get_secret_value() !='None' else None)
    def __await__(self):
        return self.initialize_database().__await__()
    async def initialize_database(self):
        retries: int = 5
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
                else:logging.critical(f'Unable to connect to the RedisDB - {disconnect}')

    async def set(self, key:uuid.UUID, value: dict| list,expire:int = timedelta(hours = load_yaml()['backgroundTasks']['scheduleExpiry'])):
        try:
            await asyncio.gather(self._pool.set(key.urn, orjson.dumps(value)),self._pool.expire(key.urn, expire))
            logging.info(f'Background Task:Cached data into schedule collection - {key}')
        except Exception as insert_db:
            logging.error(insert_db)

    async def get(self, key: uuid.UUID):
        try:
            logging.info(f'Background Task:Getting data from Redis - {key}')
            get_result = await self._pool.get(key.urn)
            if get_result:
                return orjson.loads(get_result)
            return None
        except Exception as find_error:
            logging.error(find_error)
