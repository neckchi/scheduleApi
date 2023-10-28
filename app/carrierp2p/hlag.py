from app.routers.router_config import HTTPXClientWrapper
from datetime import datetime,timedelta
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from app.carrierp2p import mapping_template
async def get_hlag_access_token(client,background_task, url: str,pw:str,user:str, client_id: str,client_secret:str):
    hlcu_token_key = uuid5(NAMESPACE_DNS, 'hlcu-token-uuid-kuehne-nagel')
    response_token = await db.get(key=hlcu_token_key)
    if not response_token:
        headers: dict = {'X-IBM-Client-Id': client_id,
                         'X-IBM-Client-Secret': client_secret,
                         'Accept': 'application/json'}
        body:dict = {'mode': "raw",'userId': user,'password': pw,'orgUnit': "HLAG"}
        response_token = await anext(HTTPXClientWrapper.call_client(method='POST',background_tasks =background_task,client=client,url=url, headers=headers,json=body,token_key=hlcu_token_key,expire=timedelta(minutes=10)))
    yield response_token['token']

async def get_hlag_p2p(client,background_task, url: str, turl: str,user:str, pw: str, client_id: str,client_secret:str,pol: str, pod: str,search_range: int,
                       etd: datetime.date = None, eta: datetime.date = None, direct_only: bool|None = None,vessel_flag:str|None = None,service: str | None = None, tsp: str | None = None):
    start_day:str = etd.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else eta.strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day:str = (etd+ timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (eta + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'earliestDepartureDateTime': start_day,'latestDepartureDateTime':end_day}) if etd else params.update({'earliestArrivalDateTime': start_day,'arrivalEndDateTime':end_day})
    params.update({'routingTypeCode': direct_only}) if direct_only is not None else...
    params.update({'vesselFlag': vessel_flag}) if vessel_flag is not None else ...
    token = await anext(get_hlag_access_token(client=client,background_task=background_task, url=turl,user=user, pw=pw, client_id= client_id,client_secret = client_secret))
    headers: dict = {'X-IBM-Client-Id': client_id,'X-IBM-Client-Secret': client_secret, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response_json = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,headers=headers))
    if response_json:
        total_schedule_list:list = []
        for task in response_json:
            first_point_from:str = task['placeOfReceipt']
            last_point_to:str = task['placeOfDelivery']
            first_etd:datetime = task['placeOfReceiptDateTime']
            last_eta:datetime = task['placeOfDeliveryDateTime']
            transit_time: int = task.get('transitTime',(datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
            first_cy_cutoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'FCO'), None)
            first_vgm_cuttoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'VCO'), None)
            first_doc_cutoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'LCO'), None)
            check_transshipment:bool = len(task['legs']) > 1
            schedule_body: dict = mapping_template.produce_schedule_body(
                carrier_code='HLCU',
                first_point_from=first_point_from,
                last_point_to=last_point_to,
                first_etd=first_etd,
                last_eta=last_eta, cy_cutoff=first_cy_cutoff, doc_cutoff=first_doc_cutoff,vgm_cutoff=first_vgm_cuttoff,
                transit_time=transit_time,
                check_transshipment=check_transshipment)
            leg_list:list = [mapping_template.produce_leg_body(
                    origin_un_name=leg['departureLocation']['locationName'],
                    origin_un_code=leg['departureLocation']['UNLocationCode'],
                    dest_un_name=leg['arrivalLocation']['locationName'],
                    dest_un_code=leg['arrivalLocation']['UNLocationCode'],
                    etd=(etd:=leg['departureDateTime']),
                    eta=(eta:=leg['arrivalDateTime']),
                    tt=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                    transport_type=str(leg['modeOfTransport']).title(),
                    transport_name=leg['vesselName'] if (vessel_imo := leg.get('vesselImoNumber')) else None,
                    reference_type='IMO' if vessel_imo and vessel_imo != '0000000' else None,
                    reference=vessel_imo if vessel_imo != '0000000' else None,
                    service_name=leg.get('serviceName'),
                    internal_voy=leg.get('importVoyageNumber'))for leg in task['legs']]
            total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
        return total_schedule_list


