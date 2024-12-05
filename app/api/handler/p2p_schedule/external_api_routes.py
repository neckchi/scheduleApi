import logging
import time
from uuid import UUID

from fastapi import BackgroundTasks, Query, Request, Response

from app.api.carrier_api import cma, hlag, iqax, maersk, msc, one, zim
from app.api.schemas.schema_request import StartDateType
from app.internal.http.http_client_manager import AsyncTaskManager, HTTPClientWrapper


async def route_to_carrier_api(product_id: UUID, client: HTTPClientWrapper, request: Request, query_params: Query,
                               response: Response, settings, port_code_mapping, background_tasks: BackgroundTasks):
    async with AsyncTaskManager() as task_group:
        start_time = time.time()
        for carriers in query_params.scac:
            # CMA carrier task
            if carriers in {'CMDU', 'ANNU', 'CHNL'} or carriers is None:
                task_group.create_task(
                    name=f'CMA_task' if carriers is None else f'{carriers}_task',
                    coro=lambda cma_scac=carriers: cma.get_cma_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.cma_url,
                        scac=cma_scac,
                        pol=port_code_mapping.get(
                            f"{cma_scac}_pol_code" if not cma_scac else 'CMDU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get(
                            f"{cma_scac}_pod_code" if not cma_scac else 'CMDU_pod_code') or query_params.point_to,
                        departure_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                        arrival_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                        search_range=query_params.search_range.duration,
                        direct_only=query_params.direct_only,
                        vessel_imo=query_params.vessel_imo,
                        tsp=query_params.tsp,
                        service=query_params.service,
                        pw=settings.cma_token.get_secret_value()))

            # APL carrier task
            if carriers == 'APLU' or carriers is None:
                task_group.create_task(
                    name=f'APLU_task',
                    coro=lambda: cma.get_cma_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.cma_url,
                        scac="APLU",
                        pol=port_code_mapping.get('APLU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('APLU_pod_code') or query_params.point_to,
                        departure_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                        arrival_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                        search_range=query_params.search_range.duration,
                        direct_only=query_params.direct_only,
                        vessel_imo=query_params.vessel_imo,
                        tsp=query_params.tsp,
                        service=query_params.service,
                        pw=settings.cma_token.get_secret_value()))

            # ONE carrier task
            if carriers == 'ONEY' or carriers is None:
                task_group.create_task(
                    name='ONE_task',
                    coro=lambda: one.get_one_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.oney_url,
                        token_url=settings.oney_turl,
                        pol=port_code_mapping.get('ONEY_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('ONEY_pod_code') or query_params.point_to,
                        start_date_type='BY_DEPARTURE_DATE' if query_params.start_date_type == StartDateType.departure else 'BY_ARRIVAL_DATE',
                        start_date=query_params.start_date,
                        direct_only=query_params.direct_only,
                        search_range=int(query_params.search_range.value),
                        tsp=query_params.tsp,
                        vessel_imo=query_params.vessel_imo,
                        service=query_params.service,
                        auth=settings.oney_auth.get_secret_value(),
                        pw=settings.oney_token.get_secret_value()
                    )
                )

            # # HMM carrier task
            # if carriers == 'HDMU' or carriers is None:
            #     task_group.create_task(
            #         name='HMM_task',
            #         coro=lambda: hmm.get_hmm_p2p(
            #             client=client,
            #             background_task=background_tasks,
            #             url=settings.hmm_url,
            #             pol=port_code_mapping.get('HDMU_pol_code') or query_params.point_from,
            #             pod=port_code_mapping.get('HDMU_pod_code') or query_params.point_to,
            #             start_date=query_params.start_date,
            #             service=query_params.service,
            #             direct_only=query_params.direct_only,
            #             vessel_imo=query_params.vessel_imo,
            #             tsp=query_params.tsp,
            #             pw=settings.hmm_token.get_secret_value(),
            #             search_range=str(query_params.search_range.value)
            #         )
            #     )

            # ZIM carrier task
            if carriers == 'ZIMU' or carriers is None:
                task_group.create_task(
                    name='ZIM_task',
                    coro=lambda: zim.get_zim_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.zim_url,
                        token_url=settings.zim_turl,
                        pol=port_code_mapping.get('ZIMU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('ZIMU_pod_code') or query_params.point_to,
                        start_date_type=query_params.start_date_type,
                        start_date=query_params.start_date,
                        direct_only=query_params.direct_only,
                        tsp=query_params.tsp,
                        search_range=query_params.search_range.duration,
                        service=query_params.service,
                        vessel_imo=query_params.vessel_imo,
                        pw=settings.zim_token.get_secret_value(),
                        zim_client=settings.zim_client.get_secret_value(),
                        zim_secret=settings.zim_secret.get_secret_value()
                    )
                )

            # MAERSK carrier task - MAEU
            if carriers == 'MAEU' or carriers is None:
                task_group.create_task(
                    name=f'MAEU_task',
                    coro=lambda: maersk.get_maersk_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.maeu_p2p,
                        location_url=settings.maeu_location,
                        cutoff_url=settings.maeu_cutoff,
                        pol=port_code_mapping.get('MAEU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('MAEU_pod_code') or query_params.point_to,
                        start_date=query_params.start_date,
                        search_range=query_params.search_range.value,
                        scac='MAEU',
                        direct_only=query_params.direct_only,
                        tsp=query_params.tsp,
                        vessel_flag=query_params.vessel_flag_code,
                        vessel_imo=query_params.vessel_imo,
                        date_type='D' if query_params.start_date_type == StartDateType.departure else 'A',
                        service=query_params.service,
                        pw=settings.maeu_token.get_secret_value(),
                        pw2=settings.maeu_token2.get_secret_value()
                    )
                )
            # MAERSK carrier task - MAEI
            if carriers == 'MAEI' or carriers is None:
                task_group.create_task(
                    name=f'MAEI',
                    coro=lambda: maersk.get_maersk_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.maeu_p2p,
                        location_url=settings.maeu_location,
                        cutoff_url=settings.maeu_cutoff,
                        pol=port_code_mapping.get('MAEI_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('MAEI_pod_code') or query_params.point_to,
                        start_date=query_params.start_date,
                        search_range=query_params.search_range.value,
                        scac='MAEI',
                        direct_only=query_params.direct_only,
                        tsp=query_params.tsp,
                        vessel_flag=query_params.vessel_flag_code,
                        vessel_imo=query_params.vessel_imo,
                        date_type='D' if query_params.start_date_type == StartDateType.departure else 'A',
                        service=query_params.service,
                        pw=settings.maeu_token.get_secret_value(),
                        pw2=settings.maeu_token2.get_secret_value()
                    )
                )

            # MSC carrier task
            if carriers == 'MSCU' or carriers is None:
                task_group.create_task(
                    name='MSC_task',
                    coro=lambda: msc.get_msc_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.mscu_url,
                        oauth=settings.mscu_oauth,
                        aud=settings.mscu_aud,
                        pol=port_code_mapping.get('MSCU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('MSCU_pod_code') or query_params.point_to,
                        start_date=query_params.start_date,
                        search_range=query_params.search_range.duration,
                        direct_only=query_params.direct_only,
                        start_date_type='POL' if query_params.start_date_type == StartDateType.departure else 'POD',
                        service=query_params.service,
                        tsp=query_params.tsp,
                        vessel_imo=query_params.vessel_imo,
                        pw=settings.mscu_rsa_key.get_secret_value(),
                        msc_client=settings.mscu_client.get_secret_value(),
                        msc_scope=settings.mscu_scope.get_secret_value(),
                        msc_thumbprint=settings.mscu_thumbprint.get_secret_value()
                    )
                )

            # COSU carrier task
            if carriers == 'OOLU' or carriers is None:
                task_group.create_task(
                    name=f'OOLU_task',
                    coro=lambda: iqax.get_iqax_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.iqax_url,
                        pol=port_code_mapping.get('OOLU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('OOLU_pol_code') or query_params.point_to,
                        departure_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                        arrival_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                        search_range=query_params.search_range.value,
                        direct_only=query_params.direct_only,
                        tsp=query_params.tsp,
                        vessel_imo=query_params.vessel_imo,
                        scac="OOLU",
                        service=query_params.service,
                        pw=settings.iqax_token.get_secret_value()
                    )
                )

            if carriers == 'COSU' or carriers is None:
                task_group.create_task(
                    name=f'COSU_task',
                    coro=lambda: iqax.get_iqax_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.iqax_url,
                        pol=port_code_mapping.get('COSU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('COSU_pol_code') or query_params.point_to,
                        departure_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.departure else None,
                        arrival_date=query_params.start_date.strftime(
                            '%Y-%m-%d') if query_params.start_date_type == StartDateType.arrival else None,
                        search_range=query_params.search_range.value,
                        direct_only=query_params.direct_only,
                        tsp=query_params.tsp,
                        vessel_imo=query_params.vessel_imo,
                        scac="COSU",
                        service=query_params.service,
                        pw=settings.iqax_token.get_secret_value()
                    )
                )

            # HLAG carrier task
            if carriers == 'HLCU' or carriers is None:
                task_group.create_task(
                    name='HLAG_task',
                    coro=lambda: hlag.get_hlag_p2p(
                        client=client,
                        background_task=background_tasks,
                        url=settings.hlcu_url,
                        client_id=settings.hlcu_client_id.get_secret_value(),
                        client_secret=settings.hlcu_client_secret.get_secret_value(),
                        pol=port_code_mapping.get('HLCU_pol_code') or query_params.point_from,
                        pod=port_code_mapping.get('HLCU_pod_code') or query_params.point_to,
                        search_range=query_params.search_range.duration,
                        etd=query_params.start_date if query_params.start_date_type == StartDateType.departure else None,
                        eta=query_params.start_date if query_params.start_date_type == StartDateType.arrival else None,
                        tsp=query_params.tsp,
                        service=query_params.service,
                        vessel_imo=query_params.vessel_imo,
                        direct_only=query_params.direct_only
                    )
                )

    final_schedules = client.gen_all_valid_schedules(
        request=request,
        response=response,
        matrix=task_group.results,
        product_id=product_id,
        point_from=query_params.point_from,
        point_to=query_params.point_to,
        background_tasks=background_tasks,
        task_exception=task_group.error
    )

    process_time = time.time() - start_time
    logging.info(
        f'total_processing_time={process_time:.2f}s total_results={response.headers.get("KN-Count-Schedules")}')

    return final_schedules
