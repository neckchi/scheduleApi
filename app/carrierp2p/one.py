from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime

async def get_one_access_token(client,background_task, url: str, auth: str, api_key: str):
    one_token_key = uuid5(NAMESPACE_DNS, 'one-token-uuid-kuehne-nagel')
    response_token = await db.get(key=one_token_key)
    if not response_token:
        headers: dict = {'apikey': api_key,
                         'Authorization': auth,
                         'Accept': 'application/json'
                         }
        response = await anext(HTTPXClientWrapper.call_client(method='POST',background_tasks=background_task,client=client,url=url, headers=headers,token_key=one_token_key,expire=timedelta(minutes=40)))
        response_token = response.json()
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
    response = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,headers=headers))
    # Performance Enhancement - No meomory is used:async generator object - schedules
    async def schedules():
        if response.status_code == 200:
            response_json: dict = response.json()
            if response_json.get('errorMessages') is None:
                schedule_type = response_json['Direct'] if response_json.get('Direct', None) else response_json['Transshipment']
                for task in schedule_type:
                    task: dict
                    service_code:str = task['serviceCode']
                    service_name:str = task['serviceName']
                    # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                    check_service: bool = service_code == service or service_name == service if service else True
                    check_transshipment: bool = True if len(task['legs']) > 1 else False
                    transshipment_port: bool = next((True for tsport in task['legs'][1:] if tsport['departureUnloc'] == tsp),False) if check_transshipment and tsp else False
                    if transshipment_port or not tsp:
                        if check_service:
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
                            schedule_body: dict = {'scac': carrier_code, 'pointFrom': first_point_from,
                                                   'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                                   'cyCutOffDate': first_cy_cutoff, 'docCutOffDate': first_doc_cutoff,
                                                   'vgmCutOffDate': first_vgm_cutoff, 'transitTime': transit_time,
                                                   'transshipment': check_transshipment}

                            # Performance Enhancement - No meomory is used:async generator object - schedule leg
                            async def schedule_leg():
                                if check_transshipment:
                                    for legs in task['legs']:
                                        transport_id = legs.get('transportID')
                                        leg_body: dict = {'pointFrom': {'locationCode': legs['departureUnloc'],
                                                                        'terminalName': legs['departureTerminal']},
                                                          'pointTo': {'locationCode': legs['arrivalUnloc'],
                                                                      'terminalName': legs['arrivalTerminal']},
                                                          'etd': legs['departureDateEstimated'],
                                                          'eta': legs['arrivalDateEstimated'],
                                                          'transitTime': round(legs['transitDurationHrsUtc'] / 24),
                                                          'transportations': {'transportType': 'Vessel',
                                                                              'transportName': legs['transportName'],
                                                                              'referenceType': None if transport_id == 'UNKNOWN' else 'IMO',
                                                                              'reference': None if transport_id == 'UNKNOWN' else transport_id},
                                                          'voyages': {'internalVoyage': legs['conveyanceNumber']},
                                                          'services': {'serviceCode': legs['serviceCode'],
                                                                       'serviceName': legs['serviceName']}}

                                        yield leg_body

                                else:
                                    leg_body: dict = {'pointFrom': {'locationCode': first_point_from,
                                                                    'terminalName': first_origin_terminal},
                                                      'pointTo': {'locationCode': last_point_to,
                                                                  'terminalName': last_destination_terminal},
                                                      'etd': first_etd, 'eta': last_eta,
                                                      'transitTime': transit_time,
                                                      'transportations': {'transportType': 'Vessel',
                                                                          'transportName': first_vessel_name,
                                                                          'referenceType': None if first_imo == 'UNKNOWN' else 'IMO',
                                                                          'reference': None if first_imo == 'UNKNOWN' else first_imo},
                                                      'cutoffs': {'cyCuttoff': first_cy_cutoff,
                                                                  'siCuttoff': first_doc_cutoff,
                                                                  'vgmCutoff': first_vgm_cutoff},
                                                      'voyages': {'internalVoyage': first_voyage},
                                                      'services': {'serviceCode': first_service_code,
                                                                   'serviceName': first_service_name}}

                                    yield leg_body

                            schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
                            yield schedule_body
                        else:
                            pass
                    else:
                        pass
                else:
                    pass
            else:
                pass

    yield [s async for s in schedules()]
