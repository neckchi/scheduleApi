from functools import lru_cache
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
import orjson
import csv

def deepget(dct: dict, *keys):
    """
    Use function to check the json properties
    """
    for key in keys:
        try:
            dct = dct[key]
        except (TypeError, KeyError):
            return None
    return dct

async def call_client(client, method:str, url: str, params:bytes = None,headers:bytes = None,json:bytes = None,data:bytes = None,stream:bool = False):
    params_dict: dict = orjson.loads(params) if params else ...
    headers_dict: dict = orjson.loads(headers) if headers else ...
    json_dict: dict = orjson.loads(json) if json else ...
    data_dict: dict = orjson.loads(data) if data else ...
    if not stream:
        response = await client.request(method=method,url=url, params=params_dict if params else None,headers=headers_dict if headers else None, json = json_dict if  json else None,data = data_dict if  data else None)
        yield response
    else:
        """
        At the moment Only Maersk('MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI') need consumer to stream the response
        """
        client_request = client.build_request(method=method, url=url, params=params_dict if params else None,headers=headers_dict if headers else None,data = data_dict if  data else None)
        stream_request = await client.send(client_request, stream=True)
        result = StreamingResponse(stream_request.aiter_lines(), background=BackgroundTask(stream_request.aclose))
        if result.status_code == 200:
            async for data in result.body_iterator:
                response = orjson.loads(data)
                yield response
        else:yield None


@lru_cache(maxsize=None)
def check_loop(file_path,scac:str,loop_code:str = None,loop_name:str = None):
    """
    Check if the loop code/loop name exists in SCT
    """
    with open(file_path, mode="r") as loop:
        reader = csv.reader(loop)
        for row in reader:
            if (loop_code and scac == row[0] and loop_code == row[1]) or (loop_name and scac == row[0] and loop_name == row[2]):
                return True
    return False
