from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from app.config import Settings
import datetime
import logging

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
            logging.info('Connected To MongoDB - P2P schedule collection')
        except Exception as disconnect:
            logging.error(f'Unable to connect to the MongoDB - {disconnect}')

    async def insert(self, result: dict):
        utc_timestamp = datetime.datetime.utcnow()
        try:
            self.collection.create_index("productid", unique = True)
            self.collection.create_index("expiry",expireAfterSeconds = 60 * 60 * 12)
            await self.collection.insert_one(dict(result, **{'expiry': utc_timestamp}))
            logging.info('Background Task:Cached the schedules into P2P schedule collection ')
        except Exception as insert_db:
            logging.error(insert_db)

    async def retrieve(self, productid: str):
        try:
            logging.info(f'Background Task:Getting schedules from MongoDB P2P schedule collection - {productid}')
            yield await self.collection.find_one({"productid":productid})
        except Exception as find_error:
            logging.error(find_error)

    # async def replace(self,id,result:dict):
    #     await self.collection.update_one({"_id": id}, {"$set": result})
