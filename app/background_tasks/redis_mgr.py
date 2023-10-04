from datetime import timedelta
from redis.asyncio import BlockingConnectionPool, Redis
from app.config import Settings
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
        try:
            self._pool = await Redis(connection_pool=self.__pool)
            await self._pool.ping()
            logging.info(f'Connected To Redis - {self._pool.connection_pool}')
            return self
        except Exception as disconnect:
            logging.error(f'Unable to connect to the Redis - {disconnect}')

    async def set(self, key:uuid, value):
        try:
            await asyncio.gather(self._pool.set(key.urn, orjson.dumps(value)),self._pool.expire(key.urn,timedelta(hours = 4)))
            logging.info('Background Task:Cached the schedules into P2P schedule collection ')
        except Exception as insert_db:
            logging.error(insert_db)

    async def get(self, key:uuid):
        try:
            logging.info(f'Background Task:Getting P2P schedules from Redis - {key}')
            yield await self._pool.get(key.urn)
        except Exception as find_error:
            logging.error(find_error)


