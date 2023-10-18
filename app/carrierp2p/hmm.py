import datetime
from app.routers.router_config import HTTPXClientWrapper


async def get_hmm_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: str, direct_only: bool|None,
                      start_date: datetime,
                      tsp: str | None = None, service: str | None = None):

    params: dict = {'fromLocationCode': pol, 'receiveTermCode': 'CY', 'toLocationCode': pod, 'deliveryTermCode': 'CY',
                    'periodDate': start_date.strftime("%Y%m%d"),
                    'weekTerm': search_range, 'webSort': 'D',
                    'webPriority':'D' if direct_only is True else 'T' if direct_only is False else 'A'}
    headers: dict = {'x-Gateway-APIKey': pw}
    response = await anext(HTTPXClientWrapper.call_client(client=client, method='POST', url=url, headers=headers,json=params))
    response_json:dict = response.json()
    async def schedules():
        if response.status_code == 200 and response_json.get('resultMessage') == 'Success':
            for task in response_json['resultData']:
                # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                check_service_code: bool = next((True for services in task['vessel'] if dict(services).get('vesselDepartureDate') and services['vesselLoop'] == service), False) if service else True
                check_transshipment: bool = True if task.get('transshipPortCode') else False
                first_pot_code = task.get('transshipPortCode')
                if (check_transshipment and tsp and first_pot_code) or not tsp:
                    if check_service_code:
                        carrier_code:str = 'HDMU'
                        transit_time:int = task['totalTransitDay']
                        first_point_from = task['loadingPortCode']
                        first_pot_code = task.get('transshipPortCode')
                        first_pol_terminal_name:str = task['loadingTerminalName']
                        first_pol_terminal_code:str = task['loadingTerminalCode']
                        first_pot_terminal_name:str = task.get('transshipTerminalName')
                        first_pot_terminal_code:str = task.get('transshipTerminalCode')
                        last_pod_terminal_name:str = task['dischargeTerminalName']
                        last_pod_terminal_code:str = task['dischargeTerminalCode']
                        last_point_to:str = task['dischargePortCode']
                        first_etd:str = task['departureDate']
                        last_eta:str = task['arrivalDate']
                        first_cy_cutoff:str = task.get('cargoCutOffTime')
                        first_doc_cutoff:str = task.get('docCutOffDate')
                        schedule_body:dict = {'scac': carrier_code, 'pointFrom': first_point_from,
                                         'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                         'cyCutOffDate': first_cy_cutoff,
                                         'docCutOffDate': first_doc_cutoff,
                                         'transitTime': transit_time,
                                         'transshipment': check_transshipment
                                              }

                        # Performance Enhancement - No meomory is used:async generator object - schedule leg
                        async def schedule_leg():
                            # Waiting for HMM IT to fill in the location code for outboundInland and inboundInland
                            if task.get('outboundInland'):
                                leg_body: dict = {
                                    'pointFrom': {'locationName': task['outboundInland']['fromLocationName'],
                                                  'locationCode': 'DEHAM',
                                                  'terminalName': task['porFacilityName'],
                                                  'terminalCode': task['porFacilityCode']
                                                  },
                                    'pointTo': {'locationName': task['outboundInland']['toLocationName'],'locationCode': 'DEBRE'},
                                    'etd': task['outboundInland']['fromLocationDepatureDate'],
                                    'eta': task['outboundInland']['toLocationArrivalDate'],
                                    'transitTime': int((datetime.datetime.fromisoformat(
                                        task['outboundInland']['toLocationArrivalDate']) - datetime.datetime.fromisoformat(
                                        task['outboundInland']['fromLocationDepatureDate'])).days),
                                    'transportations': {'transportType': task['outboundInland']['transMode']}}
                                yield leg_body
                            else:
                                pass
                            for legs in task['vessel']:
                                legs: dict
                                vessel_imo = legs.get('lloydRegisterNo')
                                vessel_name:str|None =  legs.get('vesselName')
                                if legs.get('vesselDepartureDate'):
                                    leg_body = {'pointFrom': {'locationName': legs['loadPort'],
                                                              'locationCode': first_point_from if legs['vesselSequence'] == 1 else first_pot_code,
                                                              'terminalName': first_pol_terminal_name if legs['vesselSequence'] == 1 else first_pot_terminal_name,
                                                              'terminalCode': first_pol_terminal_code if legs['vesselSequence'] == 1 else first_pot_terminal_code},
                                                'pointTo': {'locationName': legs['dischargePort'],
                                                            'locationCode': first_pot_code if check_transshipment and legs['vesselSequence'] == 1 else last_point_to,
                                                            'terminalName': first_pot_terminal_name if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_name,
                                                            'terminalCode': first_pot_terminal_code if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_code},
                                                'etd': legs['vesselDepartureDate'],
                                                'eta': legs['vesselArrivalDate'],
                                                'transitTime': int((datetime.datetime.fromisoformat(
                                                    legs['vesselArrivalDate']) - datetime.datetime.fromisoformat(
                                                    legs['vesselDepartureDate'])).days),
                                                'transportations': {
                                                    'transportType': 'Vessel' if vessel_name else 'Barge',
                                                    'transportName': vessel_name,
                                                    'referenceType': 'IMO' if vessel_imo else None,
                                                    'reference': vessel_imo},
                                                'services': {'serviceCode': legs['vesselLoop']}}
                                    voyage_num = legs.get('voyageNumber')
                                    if voyage_num:
                                        voyage_body = {'internalVoyage': voyage_num}
                                        leg_body.update({'voyages': voyage_body})
                                    yield leg_body
                            else:
                                pass
                            if task.get('inboundInland'):
                                leg_body: dict = {
                                    'pointFrom': {'locationName': task['inboundInland']['fromLocationName'],
                                                  'locationCode': 'DEHAM'},
                                    'pointTo': {'locationName': task['inboundInland']['toLocationName'],
                                                'locationCode': 'DEBRE',
                                                'terminalName': task['deliveryFacilityName'],
                                                'terminalCode': task['deliveryFaciltyCode']},
                                    'etd': task['inboundInland']['fromLocationDepatureDate'],
                                    'eta': task['inboundInland']['toLocationArrivalDate'],
                                    'transitTime': int((datetime.datetime.fromisoformat(
                                        task['inboundInland']['toLocationArrivalDate']) - datetime.datetime.fromisoformat(
                                        task['inboundInland']['fromLocationDepatureDate'])).days),
                                    'transportations': {'transportType': task['inboundInland']['transMode']}}
                                yield leg_body
                            else:
                                pass

                        schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
                        yield schedule_body
                    else:
                        pass
                else:
                    pass
        else:
            pass

    yield [s async for s in schedules()]

