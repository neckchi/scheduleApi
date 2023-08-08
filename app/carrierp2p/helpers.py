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

async def call_client(client, method:str, url: str, params:dict = None,headers:dict = None,json:dict = None,data:dict = None,stream:bool = False):
    if not stream:
        response = await client.request(method=method,url=url, params=params,headers=headers , json = json ,data = data)
        yield response
    else:
        """
        At the moment Only Maersk('MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI') need consumer to stream the response
        """
        client_request = client.build_request(method=method, url=url, params=params,headers=headers,data = data)
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
