import pymongo.errors
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from app.config import Settings
from datetime import datetime,timedelta
import logging
import uuid

class MongoDBsetting:
    client: AsyncIOMotorClient = None
    db: AsyncIOMotorDatabase = None
    collection: AsyncIOMotorCollection = None

    async def initialize_database(self):
        setting = Settings()
        logging.info('Connecting To MongoDB')
        self.client = AsyncIOMotorClient(setting.mongo_url.get_secret_value(),connect=False,uuidRepresentation='standard')
        try:
            await self.client.server_info()
            self.db = self.client['schedule']
            self.collection = self.db['p2p']

            self.collection.create_index("productid", unique = True)
            self.collection.create_index("expiry",expireAfterSeconds = 0)
            logging.info()

            logging.info('Connected To MongoDB - P2P schedule collection')
        except Exception as disconnect:
            logging.error(f'Unable to connect to the MongoDB - {disconnect}')

    async def set(self, value: dict| list,expire = timedelta(hours = 4),key:uuid.UUID|None = None):
        now_utc_timestamp = datetime.utcnow()
        insert_cache = dict({'productid': key, 'cache': value} if key else value, **{'expiry': now_utc_timestamp + expire})
        try:
            await self.collection.insert_one(insert_cache)
            logging.info('Background Task:Cached data to P2P schedule collection')
        except pymongo.errors.DuplicateKeyError:
            logging.info('Background Task:duplicated Key is skipped')
            pass
        except Exception as insert_db:
            logging.error(insert_db)

    async def get(self, key: uuid.UUID):
        try:
            logging.info(f'Background Task:Getting data from MongoDB P2P schedule collection - {key}')
            get_result = await self.collection.find_one({"productid":key})
            if get_result:
                final_result = get_result.get('cache',get_result)
                return final_result
            return None
        except Exception as find_error:
            logging.error(find_error)

