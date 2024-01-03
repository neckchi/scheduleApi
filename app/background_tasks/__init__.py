from app.background_tasks.mongo_mgr import MongoDBsetting
from app.background_tasks.redis_mgr import ClientSideCache
from app.config import load_yaml


db = ClientSideCache()  if  load_yaml()['data']['backgroundTasks']['cacheDB'] == 'Redis' else MongoDBsetting()




