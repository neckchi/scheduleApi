from app.carrierp2p.helpers import call_client


async def get_one_access_token(client, url: str, auth: str, api_key: str):
    headers: dict = {'apikey': api_key,
                     'Authorization': auth,
                     'Accept': 'application/json'
                     }
    response = await anext(call_client(method='POST',client=client,url=url, headers=headers))
    response_token = response.json()
    access_token = response_token['access_token']
    yield access_token

async def get_one_p2p(client, url: str, turl: str, pw: str, auth: str, pol: str, pod: str, search_range: int,
                      direct_only: bool|None,
                      start_date: str | None = None,
                      date_type: str | None = None, service: str | None = None, tsp: str | None = None):
    params: dict = {'originPort': pol, 'destinationPort': pod, 'searchDate': start_date,
                    'searchDateType': date_type, 'weeksOut': search_range,
                    'directOnly': 'TRUE' if direct_only is True else 'FALSE'}
    # weekout:1 ≤ value ≤ 14
    token = await anext(get_one_access_token(client=client, url=turl, auth=auth, api_key=pw))
    headers: dict = {'apikey': pw, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response = await anext(call_client(client=client, method='GET', url=url, params=params,
                                       headers=headers))
    # Performance Enhancement - No meomory is used:async generator object - schedules
    async def schedules():
        if response.status_code == 200:
            # response_json: dict = orjson.loads(response.text)
            response_json: dict = response.json()
            if response_json.get('errorMessages') is None:
                schedule_type = response_json['Direct'] if response_json.get('Direct', None) else response_json['Transshipment']
                for task in schedule_type:
                    task: dict
                    service_code = task['serviceCode']
                    service_name = task['serviceName']
                    # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                    check_service: bool = service_code == service or service_name == service if service else True
                    check_transshipment: bool = True if len(task['legs']) > 1 else False
                    transshipment_port: bool = next((True for tsport in task['legs'][1:] if tsport['departureUnloc'] == tsp),False) if check_transshipment and tsp else False
                    if transshipment_port or not tsp:
                        if check_service:
                            carrier_code = task['scac']
                            transit_time = round(task['transitDurationHrsUtc'] / 24)
                            first_point_from = task['originUnloc']
                            first_origin_terminal = task['originTerminal']
                            last_point_to = task['destinationUnloc']
                            last_destination_terminal = task['destinationTerminal']
                            first_voyage = task['voyageNumber']
                            first_vessel_name = task['vesselName']
                            first_imo = task['imoNumber']
                            first_service_code = task['serviceCode']
                            first_service_name = task['serviceName']
                            first_etd = task['originDepartureDateEstimated']
                            last_eta = task['destinationArrivalDateEstimated']
                            first_cy_cutoff = task['terminalCutoff'] if task['terminalCutoff'] != '' else None
                            first_doc_cutoff = task['docCutoff'] if task['docCutoff'] != '' else None
                            first_vgm_cutoff = task['vgmCutoff'] if task['vgmCutoff'] != '' else None
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

