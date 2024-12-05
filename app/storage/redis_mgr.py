from datetime import timedelta
from redis.asyncio import BlockingConnectionPool, Redis,WatchError
from app.internal.setting import Settings,load_yaml
from starlette.responses import JSONResponse
from typing import Optional,List,Dict
from functools import cache
import uuid
import logging
import orjson
import asyncio
import hashlib


class ClientSideCache:
    def __init__(self):
        setting = Settings()
        self.__pool = BlockingConnectionPool(host=setting.redis_host.get_secret_value(),port=setting.redis_port.get_secret_value(),db = setting.redis_db.get_secret_value(),
                                             username=setting.redis_user.get_secret_value() if setting.redis_user.get_secret_value() !='None' else None,
                                             password=setting.redis_pw.get_secret_value() if setting.redis_pw.get_secret_value() !='None' else None)
        self.port_mapping_cache = {}
    def __await__(self):
        return self.initialize_database().__await__()

    def generate_uuid_from_string(self,namespace: str, key) -> str:
        key = str(key) if not isinstance(key, str) else key
        # Generate namespace UUID using MD5 hash directly
        namespace_uuid = uuid.UUID(bytes=hashlib.md5(namespace.encode('utf-8')).digest())
        # Generate and return the UUID as a string
        return str(uuid.uuid5(namespace_uuid, key))


    async def initialize_database(self):
        retries: int = 2
        while retries > 0:
            try:
                self._pool = await Redis(connection_pool=self.__pool)
                await self._pool.ping()
                logging.info(f'Connected To Redis - {self._pool.connection_pool}',extra={'custom_attribute':None})
                await self.preload_port_code_cache(extra='beginning')
                return self
            except Exception as disconnect:
                retries -= 1
                if retries == 0:
                    raise ConnectionError(f'Unable to connect to RedisDB after retries ')
                else:
                    await asyncio.sleep(3)
                    logging.critical(f'Retry - Unable to connect to the RedisDB - {disconnect}',extra={'custom_attribute':None})
    async def preload_port_code_cache(self,extra:str|None = None):
        try:
            logging.info("Starting cache preload from Redis",extra={'custom_attribute':  None}) if extra else logging.info("Starting cache preload from Redis")
            cursor:int = 0
            while True:
                cursor, keys = await self._pool.scan(cursor=cursor, match='PORT_MAPPING*', count=100000)
                if cursor == 0:  # When cursor returns to 0, the scan is complete
                    break
            if keys:
                async with self._pool.pipeline(transaction=True) as pipe:
                    pipe.multi()
                    for key in keys:
                        pipe.hget(key, 'carrier_port_code')
                    results = await pipe.execute()
                    for key, value in zip(keys, results):
                        if value:
                            scac, kn_port_code = key.decode('utf-8').split('_')[2:]
                            self.port_mapping_cache[f"{scac}_{kn_port_code}"] = value.decode('utf-8')
            logging.info(f"Cache preload completed. Loaded {len(self.port_mapping_cache)} entries.",extra={'custom_attribute':  None} )if extra else logging.info(f"Cache preload completed. Loaded {len(self.port_mapping_cache)} entries.")
        except Exception as e:
            logging.error(f"Error during cache preload: {e}", extra={'custom_attribute': None})
    @cache
    def get_carrier_port_code_cache(self, scac: str, kn_port_code: str):
        key = f"{scac}_{kn_port_code}"
        return self.port_mapping_cache.get(key)

    async def get_carrier_port_code(self, data: List[Dict]) -> Dict:
        try:
            logging.info(f"Getting carrier port code based on the requested scac and port code")
            return {f"{record['scac']}_{record['type']}_code": self.get_carrier_port_code_cache(scac=record['scac'], kn_port_code=record['kn_port_code']) for record in data}
        except Exception as e:
            logging.error(f"Error during bulk get: {e}")
            raise
    async def refresh_port_mapping_cache(self):
        before_count = len(self.port_mapping_cache)
        self.port_mapping_cache.clear()
        self.get_carrier_port_code_cache.cache_clear()
        logging.info(f"Cleared port mapping cache from API hub. Items removed: {before_count}")
        await self.preload_port_code_cache()
        return {f"Cleared port mapping cache from API hub. Items removed: {before_count}.Loaded the latest port code mapping into API hub"}

    def build_match_pattern(self,scac=None, kn_port_code=None):
        if scac is None and kn_port_code is None:
            return 'PORT_MAPPING*'
        elif scac is None and kn_port_code:
            return f"PORT_MAPPING_*{kn_port_code}"
        elif scac and kn_port_code is None:
            return f"PORT_MAPPING_{scac}*"
        elif scac and kn_port_code:
            return f"PORT_MAPPING_{scac}_{kn_port_code}"
    async def read_port_mapping_code(self,scac:str|None = None,kn_port_code:str|None = None):
        cursor:int = 0
        logging.info(f"Starting port mapping code read based on the request:scac={scac} kn_port_code={kn_port_code}")
        try:
            while True:
                cursor, keys = await self._pool.scan(cursor=cursor,match=self.build_match_pattern(scac=scac,kn_port_code=kn_port_code),count=100000)
                if cursor == 0:  # When cursor returns to 0, the scan is complete
                    break
            logging.info(f"Keys found: {len(keys)} records")
            if keys:
                async with self._pool.pipeline(transaction=True) as pipe:
                    pipe.multi()
                    for key in keys:
                        pipe.hgetall(key)
                    redis_results = await pipe.execute()
                    final_result:list =[]
                    for original_record, redis_value in zip(keys, redis_results):
                        decode_key = original_record.decode('utf-8')
                        scac:dict = {'scac':decode_key.split('_')[2]}
                        kn_port_code:dict = {'kn_port_code':decode_key.split('_')[-1]}
                        carrier_port_code:dict = {key.decode('utf-8'): value.decode('utf-8') for key, value in redis_value.items()}
                        final_result.append(scac|kn_port_code|carrier_port_code)
                    logging.info(f"Final result contains {len(final_result)} records")
                    return final_result
        except Exception as e:
            logging.error(f"Redis error during get_all_port_mappings: {e}")
            raise

    async def delete_port_mapping_code(self, scac: str | None = None, kn_port_code: str | None = None):
        cursor: int = 0
        logging.info(f"Starting port mapping code delete based on the request:scac={scac} kn_port_code={kn_port_code}")
        try:
            while True:
                cursor, keys = await self._pool.scan(cursor=cursor, match=self.build_match_pattern(scac=scac,kn_port_code=kn_port_code), count=100000)
                if cursor == 0:  # When cursor returns to 0, the scan is complete
                    break
            logging.info(f"Keys found: {len(keys)} records")
            if keys:
                async with self._pool.pipeline(transaction=True) as pipe:
                    pipe.multi()
                    for key in keys:
                        pipe.hdel(key,'carrier_port_code')
                    redis_results = await pipe.execute()
                    logging.info(f"Deleted {len(keys)} records from RedisDB")
                    await self.refresh_port_mapping_cache()
                    return redis_results
        except Exception as e:
            logging.error(f"Redis error during delete_all_port_mappings: {e}")
            raise

    async def update_carrier_port_code(self, scac: str, kn_port_code: str, new_carrier_port_code: str):
        key = f"PORT_MAPPING_{scac}_{kn_port_code}"
        try:
            async with self._pool.pipeline(transaction=True) as pipe:
                pipe.multi()
                pipe.hset(key, "carrier_port_code", new_carrier_port_code)
                results = await pipe.execute()
            if results[0] == 0:  # If 0, it means the field was updated
                logging.info(f"Updated carrier_port_code for {key}")
                await self.refresh_port_mapping_cache()
                return f"Updated carrier_port_code for {key}"
            elif results[0] == 1:  # If 1, it means a new field was created
                logging.info(f"Created new carrier_port_code for {key}")
                await self.refresh_port_mapping_cache()
                return f"Create carrier_port_code for {key}"
            else:
                logging.warning(f"Unexpected result when updating {key}: {results[0]}")
                return False
        except Exception as e:
            logging.error(f"Redis error during update_carrier_port_code: {e}")
            raise

    async def bulk_set(self, data: list[dict]):
        number_unique_code: int = 0
        try:
            async with self._pool.pipeline(transaction=True) as pipe:
                # Use pipelining to batch insert operations
                pipe.multi()
                for record in data:
                    key = f"PORT_MAPPING_{record['scac']}_{record['kn_port_code']}"
                    # Check if the field 'carrier_port_code' exists at the given key
                    exists = await self._pool.hexists(key, "carrier_port_code")
                    if not exists:
                        pipe.hset(key, "carrier_port_code", record['carrier_port_code'])
                        number_unique_code += 1
                if pipe.command_stack:
                    await pipe.execute()
                    logging.info(f"Bulk inserted {number_unique_code} unique port code mappings into Redis")
                    await self.refresh_port_mapping_cache()
                else:
                    logging.info("No unique port code mapping in the pipeline to execute.")
        except Exception as e:
            logging.error(f"Error during bulk insert: {e}")
            raise

    async def set(self,  key: str,value: JSONResponse,expire:int = timedelta(hours = load_yaml()['data']['backgroundTasks']['scheduleExpiry']),namespace:Optional[str] = 'data'):
        hashKey = self.generate_uuid_from_string(namespace=namespace, key=key)
        async with self._pool.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(hashKey) #tells Redis to monitor this key. If this key is modified by any other client before the transaction is executed, the transaction will be aborted.
                pipe.multi() # puts the pipeline back into buffered mode. Commands issued after this point are queued up and will be executed atomically.
                redis_set = pipe.set(name=hashKey, value=orjson.dumps(value),ex=expire,nx=True) #Using nx = True to make sure the record doesnt exist and prevent us from overwriting the original record
                if redis_set is None:
                    await pipe.discard() #Flush all previously queued commands in a transaction and restores the connection state to normal
                    logging.info(f'Key:{hashKey} already exists')
                else:
                    await pipe.execute()
                    logging.info(f'Background Task:Cached {namespace} into schedule collection - {hashKey}')
            except WatchError as watch_error:
                logging.error(watch_error) # FIFO so we wont do anything as we only need the first entry to be taken if any other client is going to change the same key
            except Exception as insert_db:
                logging.error(insert_db)

    async def get(self, key: str,namespace:Optional[str] = 'data'):
        hashKey = self.generate_uuid_from_string(namespace=namespace,key=key )
        retries:int = 3
        while retries > 0:
            try:
                logging.info(f'Background Task:Getting {namespace} from Redis - {hashKey}')
                get_result = await self._pool.get(hashKey)
                if get_result:
                    return orjson.loads(get_result)
                return None
            except Exception as find_error:
                retries -= 1
                if retries == 0:
                    raise ConnectionError(f'Unable to connect to RedisDB and retrieve cache from Redis')
                else:
                    logging.critical(f'Unable to retrieve cache from RedisDB due to {find_error}')
                    await self.initialize_database()
    async def close(self):
        await self.__pool.disconnect()
        await self.__pool.aclose()