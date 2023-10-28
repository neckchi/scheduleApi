import datetime
from app.routers.router_config import HTTPXClientWrapper
from app.carrierp2p import mapping_template

async def get_hmm_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: str, direct_only: bool|None,
                      start_date: datetime,
                      tsp: str | None = None, service: str | None = None):

    params: dict = {'fromLocationCode': pol, 'receiveTermCode': 'CY', 'toLocationCode': pod, 'deliveryTermCode': 'CY',
                    'periodDate': start_date.strftime("%Y%m%d"),
                    'weekTerm': search_range, 'webSort': 'D',
                    'webPriority':'D' if direct_only is True else 'T' if direct_only is False else 'A'}
    headers: dict = {'x-Gateway-APIKey': pw}
    response_json = await anext(HTTPXClientWrapper.call_client(client=client, method='POST', url=url, headers=headers,json=params))
    if response_json and response_json.get('resultMessage') == 'Success':
        total_schedule_list: list = []
        for task in response_json['resultData']:
            check_service_code:bool=  any(services['vesselLoop'] == service for services in task['vessel'] if services.get('vesselDepartureDate') ) if service else True
            check_transshipment: bool = bool(task.get('transshipPortCode'))
            first_pot_code:str = task.get('transshipPortCode')
            if ((check_transshipment and tsp and first_pot_code) or not tsp) and check_service_code:
                carrier_code:str = 'HDMU'
                transit_time:int = task['totalTransitDay']
                first_point_from:str = task['loadingPortCode']
                first_pot_code:str = task.get('transshipPortCode')
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
                first_doc_cutoff:str = task.get('docuCutOffTime')
                schedule_body: dict = mapping_template.produce_schedule_body(
                    carrier_code=carrier_code,
                    first_point_from=first_point_from,
                    last_point_to=last_point_to,
                    first_etd=first_etd,
                    last_eta=last_eta, cy_cutoff=first_cy_cutoff, doc_cutoff=first_doc_cutoff,
                    transit_time=transit_time,
                    check_transshipment=check_transshipment)
                leg_list: list = []
                if task.get('outboundInland'):
                    leg_list.append(mapping_template.produce_leg_body(
                        origin_un_name=task['outboundInland']['fromLocationName'],
                        origin_un_code=task['outboundInland']['fromUnLocationCode'],
                        origin_term_name=task['porFacilityName'],
                        origin_term_code=task['porFacilityCode'],
                        dest_un_name=task['outboundInland']['toLocationName'],
                        dest_un_code=task['outboundInland']['toUnLocationCode'],
                        dest_term_name=first_pol_terminal_name,
                        dest_term_code=first_pol_terminal_code,
                        etd=task['outboundInland']['fromLocationDepatureDate'],
                        eta=task['outboundInland']['toLocationArrivalDate'],
                        tt=int((datetime.datetime.fromisoformat(
                            task['outboundInland']['toLocationArrivalDate']) - datetime.datetime.fromisoformat(
                            task['outboundInland']['fromLocationDepatureDate'])).days),
                        transport_type=task['outboundInland']['transMode']))

                for legs in task['vessel']:
                    vessel_imo:str = legs.get('lloydRegisterNo')
                    vessel_name:str|None =  legs.get('vesselName')
                    if legs.get('vesselDepartureDate'):
                        leg_list.append(mapping_template.produce_leg_body(
                            origin_un_name=legs['loadPort'],
                            origin_un_code=first_point_from if legs['vesselSequence'] == 1 else first_pot_code,
                            origin_term_name=first_pol_terminal_name if legs['vesselSequence'] == 1 else first_pot_terminal_name,
                            origin_term_code=first_pol_terminal_code if legs['vesselSequence'] == 1 else first_pot_terminal_code,
                            dest_un_name=legs['dischargePort'],
                            dest_un_code=first_pot_code if check_transshipment and legs['vesselSequence'] == 1 else last_point_to,
                            dest_term_name=first_pot_terminal_name if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_name,
                            dest_term_code=first_pot_terminal_code if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_code,
                            etd=legs.get('vesselDepartureDate'),
                            eta=legs.get('vesselArrivalDate'),
                            tt=int((datetime.datetime.fromisoformat(legs['vesselArrivalDate']) - datetime.datetime.fromisoformat(legs['vesselDepartureDate'])).days),
                            transport_type='Vessel' if vessel_name else 'Barge',
                            transport_name=vessel_name,
                            reference_type='IMO' if vessel_imo else None,
                            reference=vessel_imo,
                            service_code=legs.get('vesselLoop'),
                            internal_voy=legs.get('voyageNumber')))

                if task.get('inboundInland'):
                    leg_list.append(mapping_template.produce_leg_body(
                        origin_un_name=task['inboundInland']['fromLocationName'],
                        origin_un_code=task['inboundInland']['fromUnLocationCode'],
                        origin_term_name=last_pod_terminal_name,
                        origin_term_code=last_pod_terminal_code,
                        dest_un_name=task['inboundInland']['toLocationName'],
                        dest_un_code=task['inboundInland']['toUnLocationCode'],
                        dest_term_name=task['deliveryFacilityName'],
                        dest_term_code=task['deliveryFaciltyCode'],
                        etd=task['inboundInland']['fromLocationDepatureDate'],
                        eta=task['inboundInland']['toLocationArrivalDate'],
                        tt=int((datetime.datetime.fromisoformat(
                            task['inboundInland']['toLocationArrivalDate']) - datetime.datetime.fromisoformat(
                            task['inboundInland']['fromLocationDepatureDate'])).days),
                        transport_type=task['inboundInland']['transMode']))
                total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
        return total_schedule_list
