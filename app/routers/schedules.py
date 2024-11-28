import logging
import uuid
from typing import Optional, List, Annotated
from uuid import uuid5, NAMESPACE_DNS, UUID

from fastapi import APIRouter, Depends, BackgroundTasks, Request, Response, Query, HTTPException
from fastapi.params import Header

from app.background_tasks import db
from app.config import log_correlation, Settings, get_settings, load_yaml, correlation_context
from app.routers.carrier_api_router import route_to_carrier_api
from app.routers.router_config import HTTPClientWrapper, get_global_http_client_wrapper
from app.routers.security import basic_auth
from app.schemas import schema_response
from app.schemas.schema_request import QueryParams, CarrierCode

router = APIRouter(prefix='/schedules', tags=["API Point To Point Schedules"])


async def get_scac_param(
    scac: Optional[List[str]] = Query(None, description="List of carrier codes")
) -> Optional[List[str]]:
    print(f"Raw SCAC values received: {scac}")  # Debug print
    if scac:
        for code in scac:
            if code not in CarrierCode.__args__:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid SCAC code: {code}"
                )
    return scac


@router.get("/p2p", summary="Search Point To Point schedules from carriers", response_model=schema_response.Product,
            response_model_exclude_defaults=True,
            response_description='Return a list of carrier ocean products with multiple schedules')
async def get_schedules(background_tasks: BackgroundTasks,
                        request: Request,
                        response: Response,
                        query_params: Annotated[QueryParams, Query()],
                        settings: Settings = Depends(get_settings),
                        carrier_status=Depends(load_yaml),
                        credentials=Depends(basic_auth),
                        client: HTTPClientWrapper = Depends(get_global_http_client_wrapper),
                        X_Correlation_ID: str | None = Header(default=None)):
    """
    Search P2P Schedules with all the information:
    - **pointFrom/pointTo** : Provide either point code or port code in UNECE format
    - **startDateType** : StartDateType cound be either 'Departure' or 'Arrival'
    - **startDate** : it could be either ETD or ETA. this depends on the startDateTtpethe date format has to be YYYY-MM-DD
    - **searchRange** : Range in which startDateType are searched in weeks ,max 4 weeks
    - **scac** : this allow to have one or mutiple scac or even null. if null, API hub will search for all carrier p2p schedule.
    """
    correlation_id = X_Correlation_ID or str(uuid.uuid4())
    correlation_context.set(correlation_id)
    logging.setLogRecordFactory(log_correlation())
    logging.info(f'Received a request with following parameters:{request.url.query}')
    product_id: UUID = uuid5(NAMESPACE_DNS, f'p2p-api-{request.url}')
    ttl_schedule = await db.get(key=product_id, log_component='the whole schedules')
    if not ttl_schedule:
        # 👇 Having this allows for waiting for all our tasks with strong safety guarantees,logic around cancellation for failures,coroutine-safe and grouping of exceptions.
        final_schedule = await route_to_carrier_api(client=client, product_id=product_id, query_params=query_params, response=response, settings=settings, background_tasks=background_tasks)
        return final_schedule
    else:
        return ttl_schedule
