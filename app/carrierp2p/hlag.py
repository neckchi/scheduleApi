from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from app.background_tasks import db
from datetime import datetime,timedelta
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import BackgroundTasks
import asyncio



def process_response_data(response_data: dict,  service: str, tsp: str) -> list:
    total_schedule_list: list = []
    for task in response_data:
        first_point_from: str = task['placeOfReceipt']
        last_point_to: str = task['placeOfDelivery']
        first_etd: datetime = task['placeOfReceiptDateTime']
        last_eta: datetime = task['placeOfDeliveryDateTime']
        transit_time: int = task.get('transitTime', (datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
        first_cy_cutoff: datetime = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'FCO'), None)
        first_vgm_cuttoff: datetime = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'VCO'), None)
        first_doc_cutoff: datetime = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'LCO'), None)
        check_transshipment: bool = len(task['legs']) > 1
        leg_list: list = [schema_response.Leg.model_construct(
            pointFrom={'locationName': leg['departureLocation']['locationName'],
                       'locationCode': leg['departureLocation']['UNLocationCode']},
            pointTo={'locationName': leg['arrivalLocation']['locationName'],
                     'locationCode': leg['arrivalLocation']['UNLocationCode']},
            etd=(etd := leg['departureDateTime']),
            eta=(eta := leg['arrivalDateTime']),
            transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
            transportations={'transportType': str(leg['modeOfTransport']).title(),
                             'transportName': leg['vesselName'] if (vessel_imo := leg.get('vesselImoNumber')) else None,
                             'referenceType': 'IMO' if vessel_imo and vessel_imo != '0000000' else None,
                             'reference': vessel_imo if vessel_imo != '0000000' else None},
            services={'serviceName': check_service} if (check_service := leg.get('serviceName')) else None,
            voyages={'internalVoyage': internal_voy} if (internal_voy := leg.get('importVoyageNumber')) else None) for
            leg in task['legs']]
        schedule_body: dict = schema_response.Schedule.model_construct(scac='HLCU', pointFrom=first_point_from,
                                                                       pointTo=last_point_to, etd=first_etd,
                                                                       eta=last_eta, cyCutOffDate=first_cy_cutoff,
                                                                       docCutoffDate=first_doc_cutoff,
                                                                       vgmCutOffDate=first_vgm_cuttoff,
                                                                       transitTime=transit_time,
                                                                       transshipment=check_transshipment,
                                                                       legs=leg_list).model_dump(warnings=False)
        total_schedule_list.append(schedule_body)
    return total_schedule_list
async def get_hlag_access_token(client:HTTPXClientWrapper,background_task, url: str,pw:str,user:str, client_id: str,client_secret:str):
    hlcu_token_key:UUID = uuid5(NAMESPACE_DNS, 'hlcu-token-uuid-kuehne-nagel')
    response_token:dict = await db.get(key=hlcu_token_key)
    if response_token is None:
        headers: dict = {'X-IBM-Client-Id': client_id,
                         'X-IBM-Client-Secret': client_secret,
                         'Accept': 'application/json'}
        body:dict = {'mode': "raw",'userId': user,'password': pw,'orgUnit': "HLAG"}
        response_token:dict  = await anext(client.parse(method='POST',background_tasks =background_task,url=url, headers=headers,json=body,token_key=hlcu_token_key,expire=timedelta(minutes=10)))
    yield response_token['token']
async def get_hlag_p2p(client:HTTPXClientWrapper,background_task:BackgroundTasks,url: str, turl: str,user:str, pw: str, client_id: str,client_secret:str,pol: str, pod: str,search_range: int,
                       etd: datetime.date = None, eta: datetime.date = None, direct_only: bool|None = None,vessel_flag:str|None = None,service: str | None = None, tsp: str | None = None):
    start_day:str = etd.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else eta.strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day:str = (etd+ timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (eta + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'earliestDepartureDateTime': start_day,'latestDepartureDateTime':end_day}) if etd else params.update({'earliestArrivalDateTime': start_day,'arrivalEndDateTime':end_day})
    params.update({'routingTypeCode': direct_only}) if direct_only is not None else...
    params.update({'vesselFlag': vessel_flag}) if vessel_flag is not None else ...
    token = await anext(get_hlag_access_token(client=client,background_task=background_task, url=turl,user=user, pw=pw, client_id= client_id,client_secret = client_secret))
    headers: dict = {'X-IBM-Client-Id': client_id,'X-IBM-Client-Secret': client_secret, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response_json = await anext(client.parse(method='GET', url=url, params=params,headers=headers))
    if response_json:
        p2p_schedule: list = await asyncio.to_thread(process_response_data,response_data=response_json, service=service,tsp=tsp)
        return p2p_schedule



