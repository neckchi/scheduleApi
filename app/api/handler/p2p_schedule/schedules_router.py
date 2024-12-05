import logging
from typing import Annotated,get_args,Optional
from fastapi import APIRouter, Depends,BackgroundTasks,Request,Response,Query,Header
from app.storage import db
from app.internal.setting import Settings,get_settings
from app.api.schemas import schema_response
from app.api.schemas.schema_request import QueryParams,CarrierCode
from app.api.handler.p2p_schedule.external_api_routes import route_to_carrier_api
from app.internal.http.http_client_manager import HTTPClientWrapper,get_global_http_client_wrapper
from app.internal.security import basic_auth



router = APIRouter(prefix='/schedules', tags=["API Point To Point Schedules"])
@router.get("/p2p", summary="Search Point To Point schedules from carriers", response_model=schema_response.Product,
            response_model_exclude_defaults=True,
            response_description='Return a list of carrier ocean products with multiple schedules')

async def get_schedules(background_tasks: BackgroundTasks,
                        request:Request,
                        response:Response,
                        query_params: Annotated[QueryParams, Query()],
                        settings: Settings = Depends(get_settings),
                        credentials = Depends(basic_auth),
                        X_Correlation_ID: Optional[str] = Header(default=None),
                        client:HTTPClientWrapper = Depends(get_global_http_client_wrapper)):
    """
    Search P2P Schedules with all the information:
    - **pointFrom/pointTo** : Provide either point code or port code in UNECE format
    - **startDateType** : StartDateType cound be either 'Departure' or 'Arrival'
    - **startDate** : it could be either ETD or ETA. this depends on the startDateTtpethe date format has to be YYYY-MM-DD
    - **searchRange** : Range in which startDateType are searched in weeks ,max 4 weeks
    - **scac** : this allows to have one or mutiple scac or even null. if null, API hub will search for all carrier p2p schedule.
    """
    logging.info(f'Received a request with following parameters:{request.url.query}')
    product_id = db.generate_uuid_from_string(namespace="schedule product",key= request.url)
    cache_result = await db.get(namespace="schedule product",key=request.url)
    if not cache_result:
        port_code_mapping = await db.get_carrier_port_code([{'scac': carrier, 'kn_port_code': port_code,'type':'pol' if idx == 0 else 'pod'} for carrier in (get_args(CarrierCode) if  query_params.scac == [None] else query_params.scac) for idx, port_code in enumerate([query_params.point_from, query_params.point_to])])
        # 👇 Having this allows for waiting for all our tasks with strong safety guarantees,logic around cancellation for failures,coroutine-safe and grouping of exceptions.
        final_schedule = await route_to_carrier_api(client=client,product_id=product_id,request=request,query_params=query_params,response=response,
                                                    settings=settings,port_code_mapping=port_code_mapping,background_tasks=background_tasks)
        return final_schedule
    else:
        return cache_result
#