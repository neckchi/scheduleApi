import datetime
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import APIRouter, Query, status, Depends, BackgroundTasks
from app.carrierp2p import cma, one, hmm, zim, maersk, msc, iqax,hlag
from app.schemas import schema_response, schema_request
from app.background_tasks import db
from app.config import Settings,get_settings,load_yaml
from app.routers.router_config import HTTPXClientWrapper,AsyncTaskManager
from app.routers.security import basic_auth


router = APIRouter(prefix='/schedules', tags=["API Point To Point Schedules"])

@router.get("/p2p", summary="Search Point To Point schedules from carriers", response_model=schema_response.Product,
            response_model_exclude_defaults=True,
            response_description='Return a list of carrier ocean products with multiple schedules')

async def get_schedules(background_tasks: BackgroundTasks,
                        point_from: str = Query(alias='pointFrom', default=..., max_length=5,regex=r"[A-Z]{2}[A-Z0-9]{3}",example='HKHKG',description='Search by either port or point of origin'),
                        point_to: str = Query(alias='pointTo', default=..., max_length=5, regex=r"[A-Z]{2}[A-Z0-9]{3}",example='DEHAM',description="Search by either port or point of destination"),
                        start_date_type: schema_request.StartDateType = Query(alias='startDateType', default=...,description="Search by either ETD or ETA"),
                        start_date: datetime.date = Query(alias='startDate', default=...,example=datetime.datetime.now().strftime("%Y-%m-%d"),description='YYYY-MM-DD'),
                        search_range: schema_request.SearchRange = Query(alias='searchRange',description='Search range based on start date and type,max 4 weeks',default=..., example=3),
                        scac: set[schema_request.CarrierCode | None] = Query(default={None},description='Prefer to search p2p schedule by scac.Empty means searching for all API schedules'),
                        direct_only: bool | None = Query(alias='directOnly', default=None,description='Direct means only show direct schedule Else show both(direct/transshipment)type of schedule'),
                        tsp: str | None = Query(default=None, alias='transhipmentPort', max_length=5,regex=r"[A-Z]{2}[A-Z0-9]{3}",description="Filter By Transshipment Port"),
                        vessel_imo:str|None = Query(alias='vesselIMO', default=None,description='Restricts the search to a particular vessel IMO lloyds code on port of loading', max_length=7),
                        vessel_flag_code: str | None = Query(alias='vesselFlagCode', default=None, max_length=2,regex=r"[A-Z]{2}"),
                        service: str | None = Query(default=None,description='Search by either service code or service name',max_length=30),
                        settings: Settings = Depends(get_settings),
                        carrier_status = Depends(load_yaml),
                        credentials = Depends(basic_auth),
                        client:HTTPXClientWrapper = Depends(HTTPXClientWrapper.get_httpx_client_wrapper)):

    """
    Search P2P Schedules with all the information:
    - **pointFrom/pointTo** : Provide either Point or Port in UNECE format
    """
    product_id:UUID = uuid5(NAMESPACE_DNS,f'{scac}-p2p-api-{point_from}{point_to}{start_date_type}{start_date}{search_range}{tsp}{direct_only}{vessel_imo}{service}')
    ttl_schedule = await db.get(key=product_id)
    if not ttl_schedule:
        # 👇 Having this allows for waiting for all our tasks with strong safety guarantees,logic around cancellation for failures,coroutine-safe and grouping of exceptions.
        async with AsyncTaskManager() as task_group:
            for carriers in scac:
                if carrier_status['data']['activeCarriers']['cma'] and (carriers in {'CMDU', 'ANNU', 'APLU', 'CHNL', 'CSFU'} or carriers is None):
                    task_group.create_task(carrier=f'CMA_task' if carriers is None else f'{carriers}_task',coro= lambda :cma.get_cma_p2p(client=client, url=settings.cma_url, scac=carriers, pol=point_from,
                                        pod=point_to,
                                        departure_date=start_date if start_date_type == 'Departure' else None,
                                        arrival_date=start_date if start_date_type == 'Arrival'else None,
                                        search_range=search_range.duration, direct_only=direct_only,vessel_imo = vessel_imo,
                                        tsp=tsp,
                                        service=service, pw=settings.cma_token.get_secret_value()))

                if carrier_status['data']['activeCarriers']['one'] and (carriers == 'ONEY' or carriers is None):
                    task_group.create_task(carrier='ONE_task',coro=lambda :one.get_one_p2p(client=client,background_task = background_tasks, url=settings.oney_url, turl=settings.oney_turl,
                                        pol=point_from, pod=point_to, start_date=start_date,
                                        direct_only=direct_only,
                                        search_range=int(search_range.value), tsp=tsp,vessel_imo = vessel_imo,
                                        date_type='BY_DEPARTURE_DATE' if start_date_type == 'Departure' else 'BY_ARRIVAL_DATE',
                                        service=service, auth=settings.oney_auth.get_secret_value(),
                                        pw=settings.oney_token.get_secret_value()))

                # Missing Location Code from HDMU response
                if carrier_status['data']['activeCarriers']['hmm'] and (carriers == 'HDMU' or carriers is None):
                    task_group.create_task(carrier='HMM_task',coro=lambda :hmm.get_hmm_p2p(client=client, url=settings.hmm_url, pol=point_from, pod=point_to,
                                        start_date=start_date, service=service, direct_only=direct_only,vessel_imo=vessel_imo,
                                        tsp=tsp, pw=settings.hmm_token.get_secret_value(),
                                        search_range=str(search_range.value)))

                # Missing IMO code and Cut off date from ZIM response
                if carrier_status['data']['activeCarriers']['zim'] and (carriers == 'ZIMU' or carriers is None):
                    task_group.create_task(carrier='ZIM_task',coro=lambda :zim.get_zim_p2p(client=client,background_task = background_tasks, url=settings.zim_url, turl=settings.zim_turl,
                                        pol=point_from, pod=point_to, start_date=start_date,
                                        direct_only=direct_only, tsp=tsp,
                                        search_range=search_range.duration, service=service,vessel_imo=vessel_imo,
                                        pw=settings.zim_token.get_secret_value(),
                                        zim_client=settings.zim_client.get_secret_value(),
                                        zim_secret=settings.zim_secret.get_secret_value()))

                if carrier_status['data']['activeCarriers']['maersk'] and (carriers in {'MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI'} or carriers is None):
                    task_group.create_task(carrier=f'MAEU_task' if carriers is None else f'{carriers}_task',coro=lambda :maersk.get_maersk_p2p(client=client,background_task = background_tasks,url=settings.maeu_p2p,
                                              location_url=settings.maeu_location,
                                              cutoff_url=settings.maeu_cutoff,
                                              pol=point_from, pod=point_to, start_date=start_date,
                                              search_range=search_range.value, scac=carriers,
                                              direct_only=direct_only, tsp=tsp,
                                              vessel_flag=vessel_flag_code,vessel_imo=vessel_imo,
                                              date_type='D' if start_date_type == 'Departure' else 'A',
                                              service=service, pw=settings.maeu_token.get_secret_value(),
                                              pw2=settings.maeu_token2.get_secret_value()))

                if carrier_status['data']['activeCarriers']['msc'] and (carriers == 'MSCU' or carriers is None):
                    task_group.create_task(carrier='MSC_task',coro=lambda :msc.get_msc_p2p(client=client,background_task = background_tasks, url=settings.mscu_url, oauth=settings.mscu_oauth,
                                        aud=settings.mscu_aud, pol=point_from, pod=point_to,
                                        start_date=start_date, search_range=search_range.duration,
                                        direct_only=direct_only,
                                        start_date_type='POL' if start_date_type == 'Departure' else 'POD',
                                        service=service, tsp=tsp,vessel_imo=vessel_imo,
                                        pw=settings.mscu_rsa_key.get_secret_value(),
                                        msc_client=settings.mscu_client.get_secret_value(),
                                        msc_scope=settings.mscu_scope.get_secret_value(),
                                        msc_thumbprint=settings.mscu_thumbprint.get_secret_value()))

                if carrier_status['data']['activeCarriers']['iqax'] and (carriers in {'OOLU', 'COSU'} or carriers is None):
                    task_group.create_task(carrier=f'IQAX_task' if carriers is None else f'{carriers}_task',coro=lambda :iqax.get_iqax_p2p(client=client, background_task = background_tasks,url=settings.iqax_url, pol=point_from,
                                          pod=point_to,
                                          departure_date=start_date if start_date_type == 'Departure' else None,
                                          arrival_date=start_date if start_date_type == 'Arrival' else None,
                                          search_range=search_range.value, direct_only=direct_only,
                                          tsp=tsp,vessel_imo=vessel_imo,
                                          scac=carriers, service=service,
                                          pw=settings.iqax_token.get_secret_value()))

                if carrier_status['data']['activeCarriers']['hlag'] and (carriers == 'HLCU' or carriers is None):
                    task_group.create_task(carrier='HLAG_task',coro=lambda :hlag.get_hlag_p2p(client= client,background_task = background_tasks, url = settings.hlcu_url,turl=settings.hlcu_token_url,
                                          client_id= settings.hlcu_client_id.get_secret_value(),client_secret=settings.hlcu_client_secret.get_secret_value(),
                                          user= settings.hlcu_user_id.get_secret_value(),pw= settings.hlcu_password.get_secret_value(),
                                          pol=point_from,pod=point_to,search_range= search_range.duration,
                                          etd= start_date if start_date_type == 'Departure' else None ,
                                          eta =start_date if start_date_type == 'Arrival' else None,
                                          direct_only=direct_only,
                                          vessel_flag = vessel_flag_code))
                # 👇 Await ALL
            p2p_schedules = await task_group.__aexit__()
            final_schedules = client.gen_all_valid_schedules(matrix=p2p_schedules,product_id=product_id,point_from=point_from,point_to=point_to,background_tasks=background_tasks,task_exception=task_group.error)
        return final_schedules
    else:
        return ttl_schedule
