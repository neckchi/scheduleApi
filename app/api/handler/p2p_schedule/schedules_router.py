import logging
import time
from typing import Annotated, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, Response
from app.api.handler.p2p_schedule.carrier_api import cma, hlag, iqax, maersk, msc, zim, one
from app.api.schemas.schema_request import QueryParams, CarrierCode, StartDateType
from app.api.schemas.schema_response import Product
from app.internal.http.http_client_manager import HTTPClientWrapper, get_global_http_client_wrapper, AsyncTaskManager
from app.internal.security import basic_auth
from app.internal.setting import Settings, get_settings
from app.storage import db

carriers_schedule_handler: dict = {
    'CMDU': cma.get_cma_p2p,
    'ANNU': cma.get_cma_p2p,
    'CHNL': cma.get_cma_p2p,
    'APLU': cma.get_cma_p2p,
    'ONEY': one.get_one_p2p,
    'ZIMU': zim.get_zim_p2p,
    'MAEU': maersk.get_maersk_p2p,
    'MAEI': maersk.get_maersk_p2p,
    'MSCU': msc.get_msc_p2p,
    'OOLU': iqax.get_iqax_p2p,
    'COSU': iqax.get_iqax_p2p,
    'HLCU': hlag.get_hlag_p2p,
}
router = APIRouter(prefix='/schedules', tags=["API Point To Point Schedules"])


@router.get("/p2p", summary="Search Point To Point schedules from carriers", response_model=Product,
            response_model_exclude_defaults=True,
            response_description='Return a list of carrier ocean products with multiple schedules')
async def get_schedules(background_tasks: BackgroundTasks,
                        request: Request,
                        response: Response,
                        query_params: Annotated[QueryParams, Query()],
                        settings: Settings = Depends(get_settings),
                        credentials=Depends(basic_auth),
                        X_Correlation_ID: Optional[str] = Header(default=None),
                        client: HTTPClientWrapper = Depends(get_global_http_client_wrapper)):
    """
    Search P2P Schedules with all the information:
    - **pointFrom/pointTo** : Provide either point code or port code in UNECE format
    - **startDateType** : StartDateType cound be either 'Departure' or 'Arrival'
    - **startDate** : it could be either ETD or ETA. this depends on the startDateTtpethe date format has to be YYYY-MM-DD
    - **searchRange** : Range in which startDateType are searched in weeks ,max 4 weeks
    - **scac** : this allows to have one or mutiple scac or even null. if null, API hub will search for all carrier p2p schedule.
    """
    logging.info(f'Received a request with following parameters:{request.url.query}')
    product_id = db.generate_uuid_from_string(namespace="schedule product", key=request.url)
    cache_result = await db.get(namespace="schedule product", key=request.url)
    if not cache_result:
        async with AsyncTaskManager() as task_group:
            start_time = time.time()

            scac_loop = query_params.scac if query_params.scac else list(
                CarrierCode.exclude("ANNU", "CHNL"))  # ANNU and CHNL are under CMDU group

            for scac in scac_loop:
                task_group.create_task(name=f'{scac.value}_task', coro=lambda c=scac.value: carriers_schedule_handler.get(c)(
                    client=client,
                    background_task=background_tasks,
                    api_settings=settings,
                    scac=c,
                    # pol=port_code_mapping.get(f'{c}_pol_code') or query_params.point_from,
                    # pod=port_code_mapping.get(f'{c}_pod_code') or query_params.point_to,
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    start_date_type=query_params.start_date_type,
                    departure_date=query_params.start_date if query_params.start_date_type == StartDateType.departure else None,
                    arrival_date=query_params.start_date if query_params.start_date_type == StartDateType.arrival else None,
                    search_range=query_params.search_range,
                    direct_only=query_params.direct_only,
                    vessel_imo=query_params.vessel_imo,
                    tsp=query_params.tsp,
                    service=query_params.service))

        final_schedules = client.gen_all_valid_schedules(
            request=request,
            response=response,
            matrix=task_group.results,
            product_id=product_id,
            point_from=query_params.point_from,
            point_to=query_params.point_to,
            background_tasks=background_tasks,
            task_exception=task_group.error,
            failed_scac=task_group.failed_scac
        )

        process_time = time.time() - start_time
        logging.info(
            f'total_processing_time={process_time:.2f}s total_results={response.headers.get("KN-Count-Schedules")}')

        return final_schedules
    else:
        return cache_result
#
