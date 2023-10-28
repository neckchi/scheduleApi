from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime
from app.carrierp2p import mapping_template

async def get_one_access_token(client,background_task, url: str, auth: str, api_key: str):
    one_token_key = uuid5(NAMESPACE_DNS, 'one-token-uuid-kuehne-nagel')
    response_token = await db.get(key=one_token_key)
    if not response_token:
        headers: dict = {'apikey': api_key,
                         'Authorization': auth,
                         'Accept': 'application/json'
                         }
        response_token = await anext(HTTPXClientWrapper.call_client(method='POST',background_tasks=background_task,client=client,url=url, headers=headers,token_key=one_token_key,expire=timedelta(minutes=40)))
    yield response_token['access_token']

async def get_one_p2p(client, background_task,url: str, turl: str, pw: str, auth: str, pol: str, pod: str, search_range: int,
                      direct_only: bool|None,
                      start_date: datetime.date,
                      date_type: str | None = None, service: str | None = None, tsp: str | None = None):
    params: dict = {'originPort': pol, 'destinationPort': pod, 'searchDate': start_date,
                    'searchDateType': date_type, 'weeksOut': search_range,
                    'directOnly': 'TRUE' if direct_only is True else 'FALSE'}
    # weekout:1 ≤ value ≤ 14
    token = await anext(get_one_access_token(client=client,background_task=background_task, url=turl, auth=auth, api_key=pw))
    headers: dict = {'apikey': pw, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response_json = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,headers=headers))
    if response_json and response_json.get('errorMessages') is None:
        schedule_type = response_json.get('Direct', response_json['Transshipment'])
        total_schedule_list :list =[]
        for task in schedule_type:
            service_code:str = task['serviceCode']
            service_name:str = task['serviceName']
            # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
            check_service: bool = service_code == service or service_name == service if service else True
            check_transshipment: bool = len(task['legs']) > 1
            transshipment_port: bool = any(tsport['departureUnloc'] == tsp for tsport in task['legs'][1:]) if check_transshipment and tsp else False
            if (transshipment_port or not tsp )and check_service:
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
                schedule_body: dict = mapping_template.produce_schedule_body(
                    carrier_code=carrier_code,
                    first_point_from=first_point_from,
                    last_point_to=last_point_to,
                    first_etd=first_etd,
                    last_eta=last_eta, cy_cutoff=first_cy_cutoff, doc_cutoff=first_doc_cutoff,
                    vgm_cutoff=first_vgm_cutoff,
                    transit_time=transit_time,
                    check_transshipment=check_transshipment)
                leg_list: list = []
                if check_transshipment:
                    for legs in task['legs']:
                        transport_id = legs.get('transportID')
                        leg_list.append(mapping_template.produce_leg_body(
                            origin_un_code=legs['departureUnloc'],
                            origin_term_name=legs['departureTerminal'],
                            dest_un_code=legs['arrivalUnloc'],
                            dest_term_name=legs['arrivalTerminal'],
                            etd=legs['departureDateEstimated'],
                            eta=legs['arrivalDateEstimated'],
                            tt=round(legs['transitDurationHrsUtc'] / 24),
                            transport_type='Vessel',
                            transport_name=legs['transportName'],
                            reference_type= None if transport_id == 'UNKNOWN' else 'IMO',
                            reference=None if transport_id == 'UNKNOWN' else transport_id,
                            service_code=legs['serviceCode'], service_name=legs['serviceName'],
                            internal_voy=legs['conveyanceNumber']))

                else:
                    leg_list.append(mapping_template.produce_leg_body(
                        origin_un_code=first_point_from,
                        origin_term_name=first_origin_terminal,
                        dest_un_code=last_point_to,
                        dest_term_name=last_destination_terminal,
                        etd=first_etd,
                        eta=last_eta,
                        tt=transit_time,
                        cy_cutoff=first_cy_cutoff,
                        si_cutoff=first_doc_cutoff,
                        vgm_cutoff=first_vgm_cutoff,
                        transport_type='Vessel',
                        transport_name=first_vessel_name,
                        reference_type=None if first_imo == 'UNKNOWN' else 'IMO',
                        reference=None if first_imo == 'UNKNOWN' else first_imo,
                        service_code=first_service_code,service_name=first_service_name,
                        internal_voy=first_voyage))
                total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
        return total_schedule_list