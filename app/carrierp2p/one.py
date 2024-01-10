from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime

async def get_one_access_token(client:HTTPXClientWrapper,background_task, url: str, auth: str, api_key: str):
    one_token_key = uuid5(NAMESPACE_DNS, 'one-token-uuid-kuehne-nagel')
    response_token = await db.get(key=one_token_key)
    if response_token is None:
        headers: dict = {'apikey': api_key,
                         'Authorization': auth,
                         'Accept': 'application/json'
                         }
        response_token = await anext(client.parse(method='POST',background_tasks=background_task,url=url, headers=headers,token_key=one_token_key,expire=timedelta(minutes=40)))
    yield response_token['access_token']

async def get_one_p2p(client:HTTPXClientWrapper, background_task,url: str, turl: str, pw: str, auth: str, pol: str, pod: str, search_range: int,
                      direct_only: bool|None,
                      start_date: datetime.date,
                      date_type: str | None = None, service: str | None = None,vessel_imo: str | None = None, tsp: str | None = None):
    params: dict = {'originPort': pol, 'destinationPort': pod, 'searchDate': start_date,'searchDateType': date_type, 'weeksOut': search_range,'directOnly': 'TRUE' if direct_only is True else 'FALSE'}
    # weekout:1 ≤ value ≤ 14
    token = await anext(get_one_access_token(client=client,background_task=background_task, url=turl, auth=auth, api_key=pw))
    headers: dict = {'apikey': pw, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response_json = await anext(client.parse(method='GET', url=url, params=params,headers=headers))
    if response_json and response_json.get('errorMessages') is None:
        total_schedule_list: list = []
        for schedule_type in response_json:
            for task in response_json[schedule_type]:
                service_code:str = task['serviceCode']
                service_name:str = task['serviceName']
                # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                check_service: bool = service_code == service or service_name == service if service else True
                check_transshipment: bool = len(task['legs']) > 1
                transshipment_port: bool = any(tsport['departureUnloc'] == tsp for tsport in task['legs'][1:]) if check_transshipment and tsp else False
                check_vessel_imo: bool = (task['imoNumber'] == vessel_imo or any(imo for imo in task['legs'] if imo.get('transportID') == vessel_imo)) if vessel_imo else True
                if (transshipment_port or not tsp )and check_service and check_vessel_imo:
                    carrier_code:str = task['scac']
                    transit_time:int = round(task['transitDurationHrsUtc'] / 24)
                    first_point_from:str = task['originUnloc']
                    first_origin_terminal:str = task['originTerminal']
                    last_point_to:str = task['destinationUnloc']
                    last_destination_terminal:str = task['destinationTerminal']
                    first_voyage:str = task['voyageNumber']
                    first_vessel_name:str = task['vesselName']
                    first_imo:str = task['imoNumber']
                    first_service_code:str = task['serviceCode']
                    first_service_name:str = task['serviceName']
                    first_etd:str = task['originDepartureDateEstimated']
                    last_eta:str = task['destinationArrivalDateEstimated']
                    first_cy_cutoff:str = task['terminalCutoff'] if task['terminalCutoff'] != '' else None
                    first_doc_cutoff:str = task['docCutoff'] if task['docCutoff'] != '' else None
                    first_vgm_cutoff:str = task['vgmCutoff'] if task['vgmCutoff'] != '' else None
                    if check_transshipment:
                        leg_list:list = [schema_response.Leg.model_construct(
                            pointFrom={'locationCode': leg['departureUnloc'],'terminalName':leg['departureTerminal']},
                            pointTo={'locationCode': leg['arrivalUnloc'],'terminalName':leg['arrivalTerminal']},
                            etd=leg['departureDateEstimated'],
                            eta=leg['arrivalDateEstimated'],
                            transitTime=round(leg['transitDurationHrsUtc'] / 24),
                            transportations={'transportType': 'Vessel','transportName': leg['transportName'],'referenceType': None if (transport_type:=leg.get('transportID')) == 'UNKNOWN' else 'IMO',
                                             'reference': None if transport_type  == 'UNKNOWN' else transport_type},
                            services={'serviceCode': service_code,'serviceName':leg['serviceName']} if (service_code:=leg['serviceCode']) or leg['serviceName'] else None,
                            voyages={'internalVoyage': voyage_num} if (voyage_num:=leg['conveyanceNumber']) else None) for leg in task['legs']]
                    else:
                        leg_list:list = [schema_response.Leg.model_construct(
                            pointFrom={'locationCode': first_point_from,'terminalName':first_origin_terminal},
                            pointTo={'locationCode': last_point_to,'terminalName':last_destination_terminal},
                            etd=first_etd,
                            eta=last_eta,
                            transitTime=transit_time,
                            cutoffs={'cyCutoffDate': first_cy_cutoff,'docCutoffDate':first_doc_cutoff,'vgmCutoffDate':first_vgm_cutoff} if first_cy_cutoff or first_doc_cutoff or first_vgm_cutoff else None,
                            transportations={'transportType': 'Vessel','transportName': first_vessel_name,'referenceType': None if first_imo == 'UNKNOWN' else 'IMO',
                                             'reference': None if first_imo == 'UNKNOWN' else first_imo},
                            services={'serviceCode': first_service_code,'serviceName':first_service_name} if first_service_code or first_service_name else None,
                            voyages={'internalVoyage': first_voyage} if first_voyage else None)]
                    schedule_body:dict = schema_response.Schedule.model_construct(scac=carrier_code,pointFrom=first_point_from,pointTo=last_point_to,etd=first_etd,eta=last_eta,
                                                                                  cyCutOffDate=first_cy_cutoff,docCutOffDate=first_doc_cutoff,vgmCutOffDate=first_vgm_cutoff,
                                                                                  transitTime=transit_time,transshipment=check_transshipment,
                                                                                  legs=leg_list).model_dump(warnings=False)
                    total_schedule_list.append(schedule_body)
        return total_schedule_list