import asyncio
from fastapi import BackgroundTasks
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from datetime import datetime,timedelta
from uuid import uuid5,NAMESPACE_DNS
from app.background_tasks import db
from itertools import chain
from typing import Generator,Iterator


def calculate_final_times(index:int, leg_etd:str, leg_tt:int, leg_transport:str, leg_from:dict,legs_to:dict, last_eta:str):
    """Calculate the correct etd eta for each leg """
    def format_datetime(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    default_offset = timedelta(days=leg_tt if leg_tt else 0.5)
    if index == 1:
        if leg_transport == 'TRUCK':
            final_etd = format_datetime(datetime.strptime(leg_etd, "%Y-%m-%dT%H:%M:%S.000Z") - default_offset)
        else:
            final_etd = leg_etd
        final_eta = legs_to.get('eta', format_datetime(datetime.strptime(final_etd, "%Y-%m-%dT%H:%M:%S.000Z") + default_offset))
    else:
        final_eta = legs_to.get('eta', last_eta)
        final_etd = leg_from.get('etd', format_datetime(datetime.strptime(final_eta, "%Y-%m-%dT%H:%M:%S.000Z") - default_offset))
    yield final_etd, final_eta

def process_response_data(task: dict, direct_only:bool |None,vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    check_service_code:bool = any(service == service_leg['code'] for leg_service in task['leg'] if (service_leg:=leg_service.get('service'))) if service else True
    check_transshipment: bool = not task['direct']
    transshipment_port:bool = any(tsport['fromPoint']['location']['unlocode'] == tsp for tsport in task['leg'][1:]) if check_transshipment and tsp else False
    check_vessel_imo: bool = any(str(imo['vessel'].get('IMO')) == vessel_imo for imo in task['leg'] if imo.get('vessel') ) if vessel_imo else True
    if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and check_service_code and check_vessel_imo:
        first_etd:str = task['por']['etd']
        last_eta:str = task['fnd']['eta']
        leg_list:list =[]
        for index, legs in enumerate(task['leg'], start=1):
            imo_code: str  = str(legs['vessel'].get('IMO')) if legs.get('vessel') else None
            leg_pol: str = legs['fromPoint']['location']['unlocode']
            leg_pod: str = legs['toPoint']['location']['unlocode']
            vessel_name:str |None  = deepget(legs,'vessel','name')
            check_service = legs.get('service')
            leg_transport:str = legs['transportMode']
            leg_tt:int = legs.get('transitTime')
            leg_etd:str = legs['fromPoint'].get('etd', first_etd)
            if leg_pol != leg_pod:
                final_etd, final_eta = next(calculate_final_times(index=index, leg_etd=leg_etd, leg_tt=leg_tt, leg_transport=leg_transport,leg_from=legs['fromPoint'], legs_to=legs['toPoint'], last_eta=last_eta))
                leg_transit_time:int = leg_tt if leg_tt else ((datetime.fromisoformat(final_eta[:10]) - datetime.fromisoformat(final_etd[:10])).days)
                leg_list.append(schema_response.LEG_ADAPTER.dump_python({
                    'pointFrom':{'locationName': legs['fromPoint']['location']['name'],'locationCode': leg_pol,
                               'terminalName': legs['fromPoint']['location']['facility']['name'] if (check_origin_terminal:=legs['fromPoint']['location'].get('facility')) else None,
                               'terminalCode':legs['fromPoint']['location']['facility']['code'] if check_origin_terminal else None},
                    'pointTo':{'locationName': legs['toPoint']['location']['name'],'locationCode': leg_pod,
                             'terminalName': legs['toPoint']['location']['facility']['name'] if (check_des_terminal:=legs['toPoint']['location'].get('facility')) else None,
                             'terminalCode':legs['toPoint']['location']['facility']['code'] if check_des_terminal else None},
                    'etd':final_etd,
                    'eta':final_eta,
                    'transitTime':legs.get('transitTime',leg_transit_time),
                    'transportations':{'transportType': leg_transport.title(),'transportName': legs['vessel']['name'] if imo_code and  vessel_name != '---' else None,
                                     'referenceType': 'IMO' if imo_code and imo_code not in (9999999,'9999999','None') else None,'reference': None if imo_code and imo_code in (9999999,'9999999','None') else imo_code},
                    'services':{'serviceCode': legs['service']['code'],'serviceName':legs['service']['name']} if check_service else None,
                    'voyages':{'internalVoyage': internal_voyage if (internal_voyage:=legs.get('internalVoyageNumber')) else None,'externalVoyage':legs.get('externalVoyageNumber')},
                    'cutoffs':{'cyCutoffDate':cy_cutoff} if (cy_cutoff:=legs['fromPoint'].get('defaultCutoff')) and cy_cutoff <= final_etd else None},warnings=False))
            else:pass
        schedule_body: dict = schema_response.SCHEDULE_ADAPTER.dump_python({'scac': task.get('carrierScac'), 'pointFrom': task['por']['location']['unlocode'],'pointTo': task['fnd']['location']['unlocode'],
                                                                             'etd': first_etd, 'eta': last_eta, 'transitTime': task.get('transitTime'),
                                                                             'transshipment': check_transshipment, 'legs': leg_list},warnings=False)
        yield schedule_body

async def get_iqax_p2p(client:HTTPXClientWrapper,background_task:BackgroundTasks, url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool |None ,
                       tsp: str | None = None, departure_date:datetime.date = None, arrival_date: datetime.date = None,vessel_imo:str|None = None,scac: str | None = None, service: str | None = None) -> Generator:
    params: dict = {'appKey': pw, 'porID': pol, 'fndID': pod, 'departureFrom': departure_date,
                    'arrivalFrom': arrival_date, 'searchDuration': search_range}
    iqax_list: list[str] = ['OOLU', 'COSU'] if scac is None else [scac]
    iqax_response_uuid = lambda scac: uuid5(NAMESPACE_DNS,f'iqax-{params}{direct_only}{vessel_imo}{service}{tsp}{scac}')
    response_cache:list = await asyncio.gather(*(db.get(key=iqax_response_uuid(scac=sub_iqax)) for sub_iqax in iqax_list))
    check_cache: bool = any(item is None for item in response_cache)
    p2p_resp_tasks: set = {asyncio.create_task(anext(client.parse(background_tasks =background_task,token_key=iqax_response_uuid(scac=iqax),method='GET', url=url.format(iqax),params=params)))
                           for iqax,cache in zip(iqax_list,response_cache) if cache is None} if check_cache else...
    combined_p2p_schedule:list = []
    for response in (chain(asyncio.as_completed(p2p_resp_tasks),[item for item in response_cache if item is not None]) if check_cache else response_cache):
        response_json:dict = await response if check_cache and not isinstance(response, dict) else response
        if response_json:
            p2p_schedule: Generator = (schedule_result for schedule_list in response_json.get('routeGroupsList', []) for task in schedule_list['route'] for schedule_result in process_response_data(task=task,direct_only=direct_only, vessel_imo=vessel_imo, service=service,tsp=tsp))
            combined_p2p_schedule.extend(p2p_schedule)
    return combined_p2p_schedule

