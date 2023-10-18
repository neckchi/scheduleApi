import asyncio
import datetime
import httpx
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import APIRouter, Query, status, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.carrierp2p import cma, hamburgsud, one, hmm, zim, maersk, msc, iqax,hlag
from app.schemas import schema_response, schema_request
from app.background_tasks import db
from app.config import Settings
from app.routers.router_config import HTTPXClientWrapper,get_settings,flatten_list

router = APIRouter(prefix='/schedules', tags=["API Point To Point Schedules"])
@router.get("/p2p", summary="Search Point To Point schedules from carriers", response_model=schema_response.Product,
            response_model_exclude_defaults=True,
            response_description='Return a list of carrier ocean products with multiple schedules',
            responses={status.HTTP_404_NOT_FOUND: {"model": schema_response.Error}})


async def get_schedules(background_tasks: BackgroundTasks,
                        point_from: str = Query(alias='pointFrom', default=..., max_length=5,regex=r"[A-Z]{2}[A-Z0-9]{3}",example='HKHKG',description='Search by either port or point of origin'),
                        point_to: str = Query(alias='pointTo', default=..., max_length=5, regex=r"[A-Z]{2}[A-Z0-9]{3}",example='DEHAM',description="Search by either port or point of destination"),
                        start_date_type: schema_request.StartDateType = Query(alias='startDateType', default=...,description="Search by either ETD or ETA"),
                        start_date: datetime.date = Query(alias='startDate', default=...,example=datetime.datetime.now().strftime("%Y-%m-%d"),description='YYYY-MM-DD'),
                        search_range: schema_request.SearchRange = Query(alias='searchRange',description='Search range based on start date and type,max 4 weeks',default=..., example=3),
                        scac: set[schema_request.CarrierCode | None] = Query(default={None},description='Prefer to search p2p schedule by scac.Empty means searching for all API schedules'),
                        direct_only: bool | None = Query(alias='directOnly', default=None,description='Direct means only show direct schedule Else show both(direct/transshipment)type of schedule'),
                        tsp: str | None = Query(default=None, alias='transhipmentPort', max_length=5,regex=r"[A-Z]{2}[A-Z0-9]{3}",description="Filter By Transshipment Port"),
                        vessel_flag_code: str | None = Query(alias='vesselFlagCode', default=None, max_length=2,regex=r"[A-Z]{2}"),
                        service: str | None = Query(default=None,description='Search by either service code or service name'),
                        settings: Settings = Depends(get_settings),
                        client: httpx.AsyncClient = Depends(HTTPXClientWrapper.get_client)):


    """
    Search P2P Schedules with all the information:

    - **pointFrom/pointTo** : Provide either Point or Port in UNECE format

    """
    product_id:UUID = uuid5(NAMESPACE_DNS,f'{scac}-p2p-api-{point_from}{point_to}{start_date_type}{start_date}{search_range}{tsp}{direct_only}{service}')
    ttl_schedule = await db.get(key=product_id)


    if not ttl_schedule:
        # 👇 Create yield tasks with less memory, we start requesting all of them concurrently if no carrier code
        # given or mutiple carrier codes given
        async def awaitable_p2p_schedules():
            for carriers in scac:
                if carriers in {'CMDU', 'ANNU', 'APLU', 'CHNL', 'CSFU'} or carriers is None:
                    yield asyncio.create_task(anext(
                        cma.get_cma_p2p(client=client, url=settings.cma_url, scac=carriers, pol=point_from,
                                        pod=point_to,
                                        departure_date=start_date if start_date_type is schema_request.StartDateType.departure else None,
                                        arrival_date=start_date if start_date_type is schema_request.StartDateType.arrival else None,
                                        search_range=search_range.duration, direct_only=direct_only,
                                        tsp=tsp,
                                        service=service, pw=settings.cma_token.get_secret_value())))

                if carriers in {'SUDU', 'ANRM'} or carriers is None:
                    yield asyncio.create_task(anext(
                        hamburgsud.get_sudu_p2p(client=client, url=settings.sudu_url, scac=carriers,
                                                pol=point_from,
                                                pod=point_to,
                                                start_date=start_date, direct_only=direct_only, tsp=tsp,
                                                date_type='earliestDeparture' if start_date_type is schema_request.StartDateType.departure else 'latestArrival',
                                                pw=settings.sudu_token.get_secret_value())))

                if carriers == 'ONEY' or carriers is None:
                    yield asyncio.create_task(anext(
                        one.get_one_p2p(client=client,background_task = background_tasks, url=settings.oney_url, turl=settings.oney_turl,
                                        pol=point_from, pod=point_to, start_date=start_date,
                                        direct_only=direct_only,
                                        search_range=int(search_range.value[0]), tsp=tsp,
                                        date_type='BY_DEPARTURE_DATE' if start_date_type is schema_request.StartDateType.departure else 'BY_ARRIVAL_DATE',
                                        service=service, auth=settings.oney_auth.get_secret_value(),
                                        pw=settings.oney_token.get_secret_value())))

                # Missing Location Code from HDMU response
                if carriers == 'HDMU' or carriers is None:
                    yield asyncio.create_task(anext(
                        hmm.get_hmm_p2p(client=client, url=settings.hmm_url, pol=point_from, pod=point_to,
                                        start_date=start_date, service=service, direct_only=direct_only,
                                        tsp=tsp, pw=settings.hmm_token.get_secret_value(),
                                        search_range=str(search_range.value[0]))))

                # Missing IMO code and Cut off date from ZIM response
                if carriers == 'ZIMU' or carriers is None:
                    yield asyncio.create_task(anext(
                        zim.get_zim_p2p(client=client,background_task = background_tasks, url=settings.zim_url, turl=settings.zim_turl,
                                        pol=point_from, pod=point_to, start_date=start_date,
                                        direct_only=direct_only, tsp=tsp,
                                        search_range=search_range.duration, service=service,
                                        pw=settings.zim_token.get_secret_value(),
                                        zim_client=settings.zim_client.get_secret_value(),
                                        zim_secret=settings.zim_secret.get_secret_value())))

                if carriers in {'MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI'} or carriers is None:
                    yield asyncio.create_task(anext(
                        maersk.get_maersk_p2p(client=client,background_task = background_tasks,url=settings.maeu_p2p,
                                              location_url=settings.maeu_location,
                                              cutoff_url=settings.maeu_cutoff,
                                              pol=point_from, pod=point_to, start_date=start_date,
                                              search_range=search_range.value[0], scac=carriers,
                                              direct_only=direct_only, tsp=tsp,
                                              vessel_flag=vessel_flag_code,
                                              date_type='D' if start_date_type is schema_request.StartDateType.departure else 'A',
                                              service=service, pw=settings.maeu_token.get_secret_value(),
                                              pw2=settings.maeu_token2.get_secret_value())))

                if carriers == 'MSCU' or carriers is None:
                    yield asyncio.create_task(anext(
                        msc.get_msc_p2p(client=client,background_task = background_tasks, url=settings.mscu_url, oauth=settings.mscu_oauth,
                                        aud=settings.mscu_aud, pol=point_from, pod=point_to,
                                        start_date=start_date, search_range=search_range.duration,
                                        direct_only=direct_only,
                                        start_date_type='POL' if start_date_type is schema_request.StartDateType.departure else 'POD',
                                        service=service, tsp=tsp,
                                        pw=settings.mscu_rsa_key.get_secret_value(),
                                        msc_client=settings.mscu_client.get_secret_value(),
                                        msc_scope=settings.mscu_scope.get_secret_value(),
                                        msc_thumbprint=settings.mscu_thumbprint.get_secret_value())))

                if carriers in {'OOLU', 'COSU'} or carriers is None:
                    yield asyncio.create_task(anext(
                        iqax.get_iqax_p2p(client=client, url=settings.iqax_url, pol=point_from,
                                          pod=point_to,
                                          departure_date=start_date if start_date_type is schema_request.StartDateType.departure else None,
                                          arrival_date=start_date if start_date_type is schema_request.StartDateType.arrival else None,
                                          search_range=search_range.value[0], direct_only=direct_only,
                                          tsp=tsp,
                                          scac=carriers, service=service,
                                          pw=settings.iqax_token.get_secret_value())))

                if carriers == 'HLCU' or carriers is None:
                    yield asyncio.create_task(anext(
                        hlag.get_hlag_p2p(client= client,background_task = background_tasks, url = settings.hlcu_url,turl=settings.hlcu_token_url,
                                          client_id= settings.hlcu_client_id.get_secret_value(),client_secret=settings.hlcu_client_secret.get_secret_value(),
                                          user= settings.hlcu_user_id.get_secret_value(),pw= settings.hlcu_password.get_secret_value(),
                                          pol=point_from,pod=point_to,search_range= search_range.duration,
                                          etd= start_date if start_date_type is schema_request.StartDateType.departure else None ,
                                          eta =start_date if start_date_type is schema_request.StartDateType.arrival else None,
                                          direct_only=direct_only,
                                          vessel_flag = vessel_flag_code)))

        # 👇 Await ALL
        p2p_schedules: list = await asyncio.gather(*{ap2ps async for ap2ps in awaitable_p2p_schedules()})
        # 👇 Best built o(1) function to flatten_p2p the loops
        flatten_p2p:list = flatten_list(p2p_schedules)
        # flatten_p2p: iter = itertools.chain(*p2p_schedules)
        sorted_schedules = sorted(flatten_p2p, key=lambda tt: (tt['etd'][:10], tt['transitTime']))
        count_schedules = len(sorted_schedules)

        if count_schedules == 0:
            failed_response = JSONResponse(status_code=status.HTTP_404_NOT_FOUND,content=jsonable_encoder(schema_response.Error(id=product_id,error=f"{point_from}-{point_to} schedule not found")))
            failed_response.set_cookie(key='p2psession', value='fail-p2p-request')
            return failed_response


        data = schema_response.Product(
            productid=product_id,
            origin=point_from,
            destination=point_to, noofSchedule=count_schedules,
            schedules=sorted_schedules).model_dump(exclude_none=True)


        background_tasks.add_task(db.set, value=data) # for MongoDB
        # background_tasks.add_task(db.set,key=product_id,value=data) #for Redis

        return data

    else:
        return ttl_schedule
