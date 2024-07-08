from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from app.background_tasks import db
from datetime import datetime,timedelta
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import BackgroundTasks
from typing import Generator,Iterator,AsyncIterator



def process_response_data(task: dict, service: str, tsp: str) -> Iterator:
    first_point_from: str = task['placeOfReceipt']['location']['UNLocationCode']
    last_point_to: str = task['placeOfDelivery']['location']['UNLocationCode']
    first_etd: datetime = task['placeOfReceipt']['dateTime']
    last_eta: datetime = task['placeOfDelivery']['dateTime']
    transit_time: int = task.get('transitTime', (datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
    check_service_code: bool = any(service == services['carrierServiceCode'] for services in task['legs'] if services.get('carrierServiceCode')) if service else True
    check_transshipment: bool = len(task['legs']) > 1
    transshipment_port: bool = any(tsport['departure']['location']['UNLocationCode'] == tsp for tsport in task['legs']) if check_transshipment and tsp else False
    if (transshipment_port or not tsp) and (check_service_code or not service) :
        leg_list: list = [schema_response.LEG_ADAPTER.dump_python({
            'pointFrom':{'locationName': leg['departure']['location']['locationName'],
                       'locationCode': leg['departure']['location']['UNLocationCode'],
                       'terminalCode': leg['departure']['location'].get('facilitySMDGCode')},
            'pointTo':{'locationName': leg['arrival']['location']['locationName'],
                     'locationCode': leg['arrival']['location']['UNLocationCode'],
                     'terminalCode': leg['arrival']['location'].get('facilitySMDGCode')},
            'etd':(etd := leg['departure']['dateTime']),
            'eta':(eta := leg['arrival']['dateTime']),
            'transitTime':int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
            'transportations':{'transportType': str(leg.get('modeOfTransport')).title(),
                             'transportName': leg['vesselName'] if (vessel_imo := leg.get('vesselIMONumber')) else None,
                             'referenceType': 'IMO' if vessel_imo and vessel_imo != '0000000' else None,
                             'reference': vessel_imo if vessel_imo != '0000000' else None},
            'services':{'serviceCode':check_service_code, 'serviceName': leg.get('carrierServiceName')} if (check_service_code := leg.get('carrierServiceCode')) else None,
            'voyages':{'internalVoyage': internal_voy if (internal_voy := leg.get('universalExportVoyageReference')) else None}},warnings=False) for leg in task['legs']]
        schedule_body: dict = schema_response.SCHEDULE_ADAPTER.dump_python({'scac': 'HLCU', 'pointFrom': first_point_from,
                                                                        'pointTo': last_point_to, 'etd': first_etd,
                                                                        'eta': last_eta,
                                                                        'transitTime': transit_time,
                                                                        'transshipment': check_transshipment,
                                                                        'legs': leg_list},warnings=False)
        yield schedule_body
async def get_hlag_access_token(client:HTTPXClientWrapper,background_task, url: str,pw:str,user:str, client_id: str,client_secret:str) -> AsyncIterator[str]:
    hlcu_token_key:UUID = uuid5(NAMESPACE_DNS, 'hlcu-token-uuid-kuehne-nagel')
    response_token:dict = await db.get(key=hlcu_token_key)
    if response_token is None:
        headers: dict = {'X-IBM-Client-Id': client_id,
                         'X-IBM-Client-Secret': client_secret,
                         'Accept': 'application/json'}
        body:dict = {'mode': "raw",'userId': user,'password': pw,'orgUnit': "HLAG"}
        response_token:dict  = await anext(client.parse(method='POST',background_tasks =background_task,url=url, headers=headers,json=body,token_key=hlcu_token_key,expire=timedelta(minutes=55)))
    yield response_token['token']
async def get_hlag_p2p(client:HTTPXClientWrapper,background_task:BackgroundTasks,url: str, turl: str,user:str, pw: str, client_id: str,client_secret:str,pol: str, pod: str,search_range: int,
                       etd: datetime.date = None, eta: datetime.date = None, direct_only: bool|None = None,service: str | None = None, tsp: str | None = None):
    start_day:str = etd.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else eta.strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day:str = (etd+ timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (eta + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'departureDateTime:gte': start_day,'departureDateTime:lte':end_day}) if etd else params.update({'arrivalDateTime:gte': start_day,'arrivalDateTime:lte':end_day})
    params.update({'isTranshipment': not(direct_only)}) if direct_only is not None else...
    hlcu_response_uuid: UUID = uuid5(NAMESPACE_DNS, 'hlcu-response-kuehne-nagel' + str(params) + str(service) + str(tsp))
    generate_schedule = lambda data: (result for task in data for result in process_response_data(task=task, service=service, tsp=tsp))
    token = await anext(get_hlag_access_token(client=client,background_task=background_task, url=turl,user=user, pw=pw, client_id= client_id,client_secret = client_secret))
    headers: dict = {'X-IBM-Client-Id': client_id,'X-IBM-Client-Secret': client_secret, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response_json = await anext(client.parse(method='GET', url=url, params=params,headers=headers))
    if response_json:
        p2p_schedule: Generator = generate_schedule(data=response_json)
        background_task.add_task(db.set, key=hlcu_response_uuid, value=response_json)
        return p2p_schedule



