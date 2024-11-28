import logging
import time
from uuid import UUID

from fastapi import BackgroundTasks, Response, Query

from app.carrierp2p import cma, one, hmm, zim, maersk, msc, iqax, hlag
from app.config import correlation_context
from app.routers.router_config import AsyncTaskManager, HTTPClientWrapper
from app.schemas.schema_request import StartDateType


async def route_to_carrier_api(product_id: UUID, client: HTTPClientWrapper, query_params: Query, response: Response, settings, background_tasks: BackgroundTasks):
    async with AsyncTaskManager() as task_group:
        start_time = time.time()
        for carriers in query_params.scac:
            if carriers in {'CMDU', 'ANNU', 'APLU', 'CHNL'} or carriers is None:
                task_group.create_task(name='CMA_task' if carriers is None else f'{carriers}_task', coro=lambda cma_scac=carriers: cma.get_cma_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.cma_url,
                    pw=settings.cma_token.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=query_params.search_range.duration,
                    direct_only=query_params.direct_only,
                    tsp=query_params.tsp,
                    vessel_imo=query_params.vessel_imo,
                    service=query_params.service,
                    departure_date=query_params.start_date.strftime('%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                    arrival_date=query_params.start_date.strftime('%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                    scac=cma_scac
                ))

            if carriers == 'ONEY' or carriers is None:
                task_group.create_task(name='ONE_task', coro=lambda: one.get_one_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.oney_url,
                    turl=settings.oney_turl,
                    pw=settings.oney_token.get_secret_value(),
                    auth=settings.oney_auth.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=int(query_params.search_range.value),
                    direct_only=query_params.direct_only,
                    start_date_type='BY_DEPARTURE_DATE' if query_params.start_date_type == StartDateType.departure else 'BY_ARRIVAL_DATE',
                    start_date=query_params.start_date,
                    service=query_params.service,
                    vessel_imo=query_params.vessel_imo,
                    tsp=query_params.tsp
                ))

            # Missing Location Code from HDMU response
            if carriers == 'HDMU' or carriers is None:
                task_group.create_task(name='HMM_task', coro=lambda: hmm.get_hmm_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.hmm_url,
                    pw=settings.hmm_token.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=str(query_params.search_range.value),
                    direct_only=query_params.direct_only,
                    start_date=query_params.start_date,
                    tsp=query_params.tsp,
                    vessel_imo=query_params.vessel_imo,
                    service=query_params.service
                ))

            if carriers == 'ZIMU' or carriers is None:
                task_group.create_task(name='ZIM_task', coro=lambda: zim.get_zim_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.zim_url,
                    turl=settings.zim_turl,
                    pw=settings.zim_token.get_secret_value(),
                    zim_client=settings.zim_client.get_secret_value(),
                    zim_secret=settings.zim_secret.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=query_params.search_range.duration,
                    start_date_type=query_params.start_date_type,
                    start_date=query_params.start_date,
                    direct_only=query_params.direct_only,
                    vessel_imo=query_params.vessel_imo,
                    service=query_params.service,
                    tsp=query_params.tsp
                ))

            if carriers in {'MAEU', 'MAEI'} or carriers is None:
                task_group.create_task(name='MAEU_task' if carriers is None else f'{carriers}_task', coro=lambda maersk_scac=carriers: maersk.get_maersk_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.maeu_p2p,
                    location_url=settings.maeu_location,
                    cutoff_url=settings.maeu_cutoff,
                    pw=settings.maeu_token.get_secret_value(),
                    pw2=settings.maeu_token2.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    start_date=query_params.start_date,
                    search_range=query_params.search_range.value,
                    direct_only=query_params.direct_only,
                    tsp=query_params.tsp,
                    scac=maersk_scac,
                    date_type='D' if query_params.start_date_type == StartDateType.departure else 'A',
                    service=query_params.service,
                    vessel_imo=query_params.vessel_imo,
                    vessel_flag=query_params.vessel_flag_code
                ))

            if carriers == 'MSCU' or carriers is None:
                task_group.create_task(name='MSC_task', coro=lambda: msc.get_msc_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.mscu_url,
                    oauth=settings.mscu_oauth,
                    aud=settings.mscu_aud,
                    pw=settings.mscu_rsa_key.get_secret_value(),
                    msc_client=settings.mscu_client.get_secret_value(),
                    msc_scope=settings.mscu_scope.get_secret_value(),
                    msc_thumbprint=settings.mscu_thumbprint.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=query_params.search_range.duration,
                    start_date_type='POL' if query_params.start_date_type == StartDateType.departure else 'POD',
                    start_date=query_params.start_date,
                    direct_only=query_params.direct_only,
                    vessel_imo=query_params.vessel_imo,
                    service=query_params.service,
                    tsp=query_params.tsp
                ))

            if carriers in {'OOLU', 'COSU'} or carriers is None:
                task_group.create_task(name='IQAX_task' if carriers is None else f'{carriers}_task', coro=lambda cosco_scac=carriers: iqax.get_iqax_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.iqax_url,
                    pw=settings.iqax_token.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=query_params.search_range.value,
                    direct_only=query_params.direct_only,
                    tsp=query_params.tsp,
                    departure_date=query_params.start_date.strftime('%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                    arrival_date=query_params.start_date.strftime('%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                    vessel_imo=query_params.vessel_imo,
                    scac=cosco_scac,
                    service=query_params.service
                ))

            if carriers == 'HLCU' or carriers is None:
                task_group.create_task(name='HLAG_task', coro=lambda: hlag.get_hlag_p2p(
                    client=client,
                    background_task=background_tasks,
                    url=settings.hlcu_url,
                    client_id=settings.hlcu_client_id.get_secret_value(),
                    client_secret=settings.hlcu_client_secret.get_secret_value(),
                    pol=query_params.point_from,
                    pod=query_params.point_to,
                    search_range=query_params.search_range.duration,
                    etd=query_params.start_date if query_params.start_date_type == StartDateType.departure else None,
                    eta=query_params.start_date if query_params.start_date_type == StartDateType.arrival else None,
                    direct_only=query_params.direct_only,
                    service=query_params.service,
                    tsp=query_params.tsp,
                    vessel_imo=query_params.vessel_imo
                ))
    correlation = correlation_context.get()
    final_schedules = client.gen_all_valid_schedules(response=response, correlation=correlation, matrix=task_group.results, product_id=product_id, point_from=query_params.point_from, point_to=query_params.point_to, background_tasks=background_tasks, task_exception=task_group.error)
    process_time = time.time() - start_time
    logging.info(f'total_processing_time={process_time:.2f}s total_results={response.headers.get("KN-Count-Schedules")}')
    return final_schedules
