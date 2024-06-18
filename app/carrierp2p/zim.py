import datetime
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import BackgroundTasks
from typing import Generator,Iterator,AsyncIterator
from functools import lru_cache


TRANSPORT_TYPE: dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel'}
CARRIER_CODE: str = 'ZIMU'

@lru_cache(maxsize=None)
def map_imo(leg_imo:str|None, vessel_name:str|None,line:str|None, transport:str) ->str:
    """Map the transportation Details"""
    if leg_imo and vessel_name != 'TO BE NAMED' and transport != 'Truck':
        return leg_imo
    elif (line == 'UNK' and leg_imo is None and transport != 'Truck') or transport == 'Feeder':
        return '9'
    elif transport == 'Truck':
        return '3'
    else:
        return '1'
def process_response_data(task: dict, direct_only:bool |None,vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    check_service_code: bool = any(service == services['line'] for services in task['routeLegs'] if services.get('voyage')) if service else True
    check_transshipment: bool = task['routeLegCount'] > 1
    check_vessel_imo: bool = any(imo for imo in task['routeLegs'] if imo.get('lloydsCode') == vessel_imo) if vessel_imo else True
    transshipment_port: bool = any(tsport['departurePort'] == tsp for tsport in task['routeLegs'][1:]) if check_transshipment and tsp else False
    if (transshipment_port or not tsp) and (direct_only is None or direct_only != check_transshipment) and (check_service_code or not service) and check_vessel_imo:
        transit_time: int = task['transitTime']
        first_point_from: str = task['departurePort']
        check_nearest_pol_etd:tuple = next((leg['legOrder'],leg['departureDate']) for leg in task['routeLegs'][::-1] if leg['departurePort'] == first_point_from)
        last_point_to: str = task['arrivalPort']
        last_eta: str = task['arrivalDate']
        schedule_body: dict = schema_response.Schedule.model_construct(scac=CARRIER_CODE,pointFrom=first_point_from,pointTo=last_point_to, etd=check_nearest_pol_etd[1],
           eta=last_eta,
           transitTime=transit_time,
           transshipment=check_transshipment,
           legs = [schema_response.Leg.model_construct(pointFrom={'locationName': leg['departurePortName'],
                                                                'locationCode': leg['departurePort']},
                                                     pointTo={'locationName': leg['arrivalPortName'],
                                                              'locationCode': leg['arrivalPort']},
                                                     etd=(etd := leg['departureDate']),
                                                     eta=(eta := leg['arrivalDate']),
                                                     transitTime=int((datetime.datetime.fromisoformat(eta) - datetime.datetime.fromisoformat(etd)).days),
                                                     transportations={'transportType': (transport:=TRANSPORT_TYPE.get(leg['vesselName'],'Vessel')),
                                                                      'transportName': (vessel_name :=leg['vesselName']),
                                                                      'referenceType': 'IMO',
                                                                      'reference':  map_imo(leg_imo = leg.get('lloydsCode'),vessel_name = vessel_name,line=leg.get('line'),transport=transport )},
                                                     services={'serviceCode': leg['line']} if (voyage_num := leg.get('voyage')) else None,
                                                     cutoffs={'cyCutoffDate': cyoff,'docCutoffDate': leg.get('docClosingDate'),
                                                              'vgmCutoffDate': leg.get('vgmClosingDate')} if (cyoff := leg.get('containerClosingDate')) or leg.get('docClosingDate') or leg.get('vgmClosingDate') else None,
                                                     voyages={'internalVoyage': voyage_num + leg['leg'] if voyage_num else None,'externalVoyage': leg.get('consortSailingNumber')})
                   for leg in task['routeLegs'] if leg['legOrder'] >= check_nearest_pol_etd[0]]).model_dump(warnings=False)
        yield schedule_body


async def get_zim_access_token(client:HTTPXClientWrapper,background_task:BackgroundTasks, url: str, api_key: str, client_id: str, secret: str) -> AsyncIterator[str]:
    zim_token_key:UUID = uuid5(NAMESPACE_DNS, 'zim-token-uuid-kuehne-nagel2')
    response_token:dict = await db.get(key=zim_token_key)
    if response_token is None:
        headers: dict = {'Ocp-Apim-Subscription-Key': api_key}
        params: dict = {'grant_type': 'client_credentials', 'client_id': client_id,'client_secret': secret, 'scope': 'Vessel Schedule'}
        response_token:dict = await anext(client.parse(background_tasks=background_task,method='POST',url=url, headers=headers, data=params,token_key=zim_token_key,expire=datetime.timedelta(minutes=55)))
    yield response_token['access_token']


async def get_zim_p2p(client:HTTPXClientWrapper, background_task:BackgroundTasks,url: str, turl: str, pw: str, zim_client: str, zim_secret: str, pol: str, pod: str,
                      search_range: int,start_date_type: str,start_date: datetime.datetime.date, direct_only: bool |None,vessel_imo:str|None = None, service: str | None = None, tsp: str | None = None):
    params: dict = {'originCode': pol, 'destCode': pod, 'fromDate': start_date,'toDate': (start_date + datetime.timedelta(days=search_range)).strftime("%Y-%m-%d"), 'sortByDepartureOrArrival': start_date_type}
    zim_response_uuid: UUID = uuid5(NAMESPACE_DNS,'zim-response-kuehne-nagel' + str(params) + str(direct_only) + str(vessel_imo) + str(service) + str(tsp))
    response_cache = await db.get(key=zim_response_uuid)
    generate_schedule = lambda data: (result for task in data['response']['routes'] for result in process_response_data(task=task, direct_only=direct_only, vessel_imo=vessel_imo, service=service, tsp=tsp))
    if response_cache:
        p2p_schedule: Generator = generate_schedule(data=response_cache)
        return p2p_schedule
    token:str = await anext(get_zim_access_token(client=client,background_task=background_task, url=turl, api_key=pw, client_id=zim_client, secret=zim_secret))
    headers: dict = {'Ocp-Apim-Subscription-Key': pw, 'Authorization': f'Bearer {token}','Accept': 'application/json'}
    response_json:dict = await anext(client.parse(method='GET', url=url, params=params,headers=headers))
    if response_json:
        p2p_schedule: Generator =  generate_schedule(data=response_json)
        background_task.add_task(db.set, key=zim_response_uuid,value=response_json)
        return p2p_schedule

