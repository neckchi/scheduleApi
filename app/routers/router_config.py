from functools import cache
from app import config
from fastapi import HTTPException
import httpx
import logging


@cache
def get_settings():
    """
    Reading a file from disk is normally a costly (slow) operation
    so we  want to do it only once and then re-use the same settings object, instead of reading it for each request.
    And this is exactly why we need to use python in built wrapper functions - cache for caching the carrier credential
    """
    return config.Settings()


##Creating new session for each request but this would probably incur performance overhead issue.
##even so it also has its own advantage like fault islation, increased flexibility to each request and avoid concurrency issues.
async def get_client():
    timeout = httpx.Timeout(50.0, read=None, connect=60.0)
    limits = httpx.Limits(max_connections=None)
    """
    the reason im doing this is make sure we can yield the client to endpoint before start and explicitly close the
    client when the request is done in order to avoid any concurency issue. When we call get_schedules, then FastAPI framworks will handle dependency injection
    and the context management for it https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-with-yield/

    FastAPI dependancy injection allows us to use generator functions as dependenacy
    """
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout, limits=limits) as client:
            # yield the client to the endpoint function
            logging.info(f'Client Session Started')
            yield client
            logging.info(f'Client Session Closed')
            # close the client when the request is done
    except Exception as e:
        print(e)
        logging.error(f'An error occured while making the request {e}')
        raise HTTPException(status_code=500,detail='An error occured while creating the client')



