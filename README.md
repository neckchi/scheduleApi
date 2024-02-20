##ReadmeFile###
**P2P Schedules API Facade**

Facade which aggregates the P2P Schedules APIs of the following Carriers:

ANNU, ANRM, APLU, CHNL, CMDU, COSU, HDMU, MAEI, MAEU, MSCU, ONEY, OOLU,ZIMU,HLCU

Other Carriers currently do not offer such an API.

The Facade provides a consistent interface for requests and responses. A Swagger doc decribing this interface is provided, on localhost see: localhost:8000/docs#/API Point To Point Schedules/get_schedules_schedules_p2p_get

Tested under Python 3.11 (see Dockerfile).

For a list of dependencies refer to requirements.txt.

Results are cached in a remote MongoDB based on carrierp2p setting

**TODO:** Currently the .env file contains several secrets, these should be removed from there. Locally the need to be stored in a gitignored file, in OCP they can be provided via Secret.

**TODO:** In mongo_mgr.py there are commented out MongoDB index creations. In theory, they could be left in the code, as the index is not recreated if it already exists. But if the index options change (e.g. the expiry time), recreating the index throws an exception. There this index handling should be taken care of separately.

**TODO:** If we use redis_mgr.py,please setup redis, put the credential into env file ,uncomment the redis credential in config.py and change cacheDB to RedisDB in configmap.yaml
