import datetime
from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response

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
                transit_time:int = task.get('totalTransitDay')
                first_point_from:str = task.get('loadingPortCode')
                first_pot_code:str = task.get('transshipPortCode')
                first_pol_terminal_name:str = task.get('loadingTerminalName')
                first_pol_terminal_code:str = task.get('loadingTerminalCode')
                first_pot_terminal_name:str = task.get('transshipTerminalName')
                first_pot_terminal_code:str = task.get('transshipTerminalCode')
                last_pod_terminal_name:str = task.get('dischargeTerminalName')
                last_pod_terminal_code:str = task.get('dischargeTerminalCode')
                last_point_to:str = task.get('dischargePortCode')
                first_etd:str = task.get('departureDate')
                last_eta:str = task.get('arrivalDate')
                first_cy_cutoff:str = task.get('cargoCutOffTime')
                first_doc_cutoff:str = task.get('docuCutOffTime')
                #outbound
                leg_list:list = [schema_response.Leg.model_construct(
                    pointFrom={'locationName': task['outboundInland']['fromLocationName'],
                               'locationCode': task['outboundInland']['fromUnLocationCode'],
                               'terminalName': task['porFacilityName'],
                               'terminalCode': task['porFacilityCode']},
                    pointTo={'locationName': task['outboundInland']['toLocationName'],
                             'locationCode': task['outboundInland']['toUnLocationCode'],
                             'terminalName': first_pol_terminal_name,
                             'terminalCode': first_pol_terminal_code},
                    etd=(outbound_etd:=task['outboundInland']['fromLocationDepatureDate']),
                    eta=(outbound_eta:=task['outboundInland']['toLocationArrivalDate']),
                    transitTime=int((datetime.datetime.fromisoformat(outbound_eta) - datetime.datetime.fromisoformat(outbound_etd)).days),
                    transportations={'transportType': task['outboundInland']['transMode']})] if task.get('outboundInland') else []
                #main routing
                leg_list += [schema_response.Leg.model_construct(
                                pointFrom={'locationName': legs['loadPort'],
                                           'locationCode': first_point_from if legs['vesselSequence'] == 1 else first_pot_code,
                                           'terminalName': first_pol_terminal_name if legs['vesselSequence'] == 1 else first_pot_terminal_name,
                                           'terminalCode':first_pol_terminal_code if legs['vesselSequence'] == 1 else first_pot_terminal_code},
                                pointTo={'locationName': legs['dischargePort'],
                                         'locationCode': first_pot_code if check_transshipment and legs['vesselSequence'] == 1 else last_point_to,
                                         'terminalName': first_pot_terminal_name if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_name,
                                         'terminalCode':first_pot_terminal_code if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_code},
                                etd=etd,
                                eta=(eta:=legs.get('vesselArrivalDate')),
                                transitTime=int((datetime.datetime.fromisoformat(eta) - datetime.datetime.fromisoformat(etd)).days),
                                transportations={'transportType': 'Vessel' if (vessel_name:=legs.get('vesselName')) else 'Feeder',
                                                 'transportName': vessel_name,
                                                 'referenceType': 'IMO' if (vessel_imo:=legs.get('lloydRegisterNo')) else None,
                                                 'reference': vessel_imo},
                                services={'serviceCode': check_service} if (check_service:=legs.get('vesselLoop')) else None,
                                voyages={'internalVoyage': internal_voy} if (internal_voy:= legs.get('voyageNumber')) else None) for legs in task['vessel'] if (etd:=legs.get('vesselDepartureDate'))]
                # inbound
                leg_list += [schema_response.Leg.model_construct(
                    pointFrom={'locationName': task['inboundInland']['fromLocationName'],
                               'locationCode': task['inboundInland']['fromUnLocationCode'],
                               'terminalName': last_pod_terminal_name,
                               'terminalCode': last_pod_terminal_code},
                    pointTo={'locationName': task['inboundInland']['toLocationName'],
                             'locationCode': task['inboundInland']['toUnLocationCode'],
                             'terminalName': task['deliveryFacilityName'],
                             'terminalCode': task['deliveryFaciltyCode']},
                    etd=(inbound_etd:=task['inboundInland']['fromLocationDepatureDate']),
                    eta=(inbound_eta:=task['inboundInland']['toLocationArrivalDate']),
                    transitTime=int((datetime.datetime.fromisoformat(inbound_eta) - datetime.datetime.fromisoformat(inbound_etd)).days),
                    transportations={'transportType': task['inboundInland']['transMode']})] if task.get('inboundInland') else []
                schedule_body: dict = schema_response.Schedule.model_construct(scac=carrier_code,pointFrom=first_point_from,pointTo=last_point_to, etd=first_etd,eta=last_eta,
                                                                               cyCutOffDate=first_cy_cutoff,docCutoffDate=first_doc_cutoff,transitTime=transit_time,
                                                                               transshipment=check_transshipment,legs=leg_list).model_dump(warnings=False)
                total_schedule_list.append(schedule_body)
        return total_schedule_list
