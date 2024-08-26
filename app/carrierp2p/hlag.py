from app.routers.router_config import HTTPClientWrapper
from app.schemas import schema_response
from app.background_tasks import db
from datetime import datetime,timedelta
from fastapi import BackgroundTasks
from typing import Generator,Iterator


def process_leg_data(leg_task:list)->list:
    leg_list: list = [schema_response.LEG_ADAPTER.dump_python({
        'pointFrom': {'locationName': leg['departure']['location']['locationName'],
                      'locationCode': leg['departure']['location']['UNLocationCode'],
                      'terminalCode': leg['departure']['location'].get('facilitySMDGCode')},
        'pointTo': {'locationName': leg['arrival']['location']['locationName'],
                    'locationCode': leg['arrival']['location']['UNLocationCode'],
                    'terminalCode': leg['arrival']['location'].get('facilitySMDGCode')},
        'etd': (etd := leg['departure']['dateTime']),
        'eta': (eta := leg['arrival']['dateTime']),
        'transitTime': int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
        'transportations': {'transportType': str(leg.get('modeOfTransport')).title(),
                            'transportName': leg['vesselName'] if (vessel_imo := leg.get('vesselIMONumber')) else None,
                            'referenceType': 'IMO' if vessel_imo and vessel_imo != '0000000' else None,
                            'reference': vessel_imo if vessel_imo and vessel_imo != '0000000' else None},
        'services': {'serviceCode': check_service_code, 'serviceName': leg.get('carrierServiceName')} if (check_service_code := leg.get('carrierServiceCode')) else None,
        'voyages': {'internalVoyage': internal_voy if (internal_voy := leg.get('universalExportVoyageReference')) else None}},warnings=False) for leg in leg_task]
    return leg_list

def process_schedule_data(task: dict, service: str, tsp: str) -> Iterator:
    first_point_from: str = task['placeOfReceipt']['location']['UNLocationCode']
    last_point_to: str = task['placeOfDelivery']['location']['UNLocationCode']
    first_etd: datetime = task['placeOfReceipt']['dateTime']
    last_eta: datetime = task['placeOfDelivery']['dateTime']
    transit_time: int = task.get('transitTime', (datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
    check_service_code: bool = any(service == services['carrierServiceCode'] for services in task['legs'] if services.get('carrierServiceCode')) if service else True
    check_transshipment: bool = len(task['legs']) > 1
    transshipment_port: bool = any(tsport['departure']['location']['UNLocationCode'] == tsp for tsport in task['legs']) if check_transshipment and tsp else False
    if (transshipment_port or not tsp) and (check_service_code or not service) :
        schedule_body: dict = schema_response.SCHEDULE_ADAPTER.dump_python({'scac': 'HLCU', 'pointFrom': first_point_from,'pointTo': last_point_to, 'etd': first_etd,
                                                                        'eta': last_eta,'transitTime': transit_time,
                                                                        'transshipment': check_transshipment,'legs': process_leg_data(leg_task=task['legs'])},warnings=False)
        yield schedule_body
async def get_hlag_p2p(client:HTTPClientWrapper,background_task:BackgroundTasks,url: str, client_id: str,client_secret:str,pol: str, pod: str,search_range: int,
                       etd: datetime.date = None, eta: datetime.date = None, direct_only: bool|None = None,service: str | None = None, tsp: str | None = None):
    start_day:str = etd.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else eta.strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day:str = (etd+ timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (eta + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'departureDateTime:gte': start_day,'departureDateTime:lte':end_day}) if etd else params.update({'arrivalDateTime:gte': start_day,'arrivalDateTime:lte':end_day})
    params.update({'isTranshipment': not(direct_only)}) if direct_only is not None else...
    generate_schedule = lambda data: (result for task in data for result in process_schedule_data(task=task, service=service, tsp=tsp))
    response_cache = await db.get(scac='hlcu', params=params, original_response=True,log_component='hlcu original response file')
    if response_cache:
        p2p_schedule: Generator = generate_schedule(data=response_cache)
        return p2p_schedule
    headers: dict = {'X-IBM-Client-Id': client_id, 'X-IBM-Client-Secret': client_secret, 'Accept': 'application/json'}
    response_json = await anext(client.parse(scac='hlag',method='GET', url=url, params=params,headers=headers))
    if response_json:
        p2p_schedule: Generator = generate_schedule(data=response_json)
        background_task.add_task(db.set,original_response=True,scac='hlcu', params=params, value=response_json,log_component='hlag original response file')
        return p2p_schedule



