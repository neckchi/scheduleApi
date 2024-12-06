import logging
import time
from uuid import UUID

from fastapi import BackgroundTasks, Query, Request, Response

from app.api.carrier_api import cma, hlag, iqax, maersk, msc, one, zim
from app.api.schemas.schema_request import StartDateType, CarrierCode
from app.internal.http.http_client_manager import AsyncTaskManager, HTTPClientWrapper
from app.internal.setting import Settings

carriers_schedule_map: dict = {
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


async def route_to_carrier_api(product_id: UUID, client: HTTPClientWrapper, request: Request, query_params: Query,
                               response: Response, settings: Settings, background_tasks: BackgroundTasks):
    async with AsyncTaskManager() as task_group:
        start_time = time.time()

        scac_loop = query_params.scac if query_params.scac else list(
            CarrierCode.exclude("ANNU", "CHNL"))  # ANNU and CHNL are under CMDU group
        for scac in scac_loop:
            task_group.create_task(name=f'{scac.value}_task', coro=lambda c=scac.value: carriers_schedule_map.get(c)(
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
