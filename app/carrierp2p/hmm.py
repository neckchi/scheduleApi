import datetime
from app.routers.router_config import HTTPClientWrapper
from app.schemas import schema_response
from app.background_tasks import db
from typing import Generator,Iterator
from fastapi import BackgroundTasks

def process_leg_data(schedule_task:dict,last_point_to:str,check_transshipment:str|None)->list:
    first_pol_terminal_name: str = schedule_task.get('loadingTerminalName')
    first_pol_terminal_code: str = schedule_task.get('loadingTerminalCode')
    first_pot_terminal_name: str = schedule_task.get('transshipTerminalName')
    first_pot_terminal_code: str = schedule_task.get('transshipTerminalCode')
    last_pod_terminal_name: str = schedule_task.get('dischargeTerminalName')
    last_pod_terminal_code: str = schedule_task.get('dischargeTerminalCode')
    first_cy_cutoff: str = schedule_task.get('cargoCutOffTime')
    first_doc_cutoff: str = schedule_task.get('docuCutOffTime')
    # outbound
    leg_list: list = [schema_response.LEG_ADAPTER.dump_python({
        'pointFrom': {'locationName': schedule_task['outboundInland']['fromLocationName'],
                      'locationCode': schedule_task['outboundInland']['fromUnLocationCode'],
                      'terminalName': schedule_task['porFacilityName'],
                      'terminalCode': schedule_task['porFacilityCode']},
        'pointTo': {'locationName': schedule_task['outboundInland']['toLocationName'],
                    'locationCode': schedule_task['outboundInland']['toUnLocationCode'],
                    'terminalName': first_pol_terminal_name,
                    'terminalCode': first_pol_terminal_code},
        'etd': (outbound_etd := schedule_task['outboundInland']['fromLocationDepatureDate']),
        'eta': (outbound_eta := schedule_task['outboundInland']['toLocationArrivalDate']),
        'transitTime': int((datetime.datetime.fromisoformat(outbound_eta) - datetime.datetime.fromisoformat(outbound_etd)).days),
        'transportations': {'transportType': schedule_task['outboundInland']['transMode']},
        'voyages': {'internalVoyage': 'NA'}}, warnings=False)] if schedule_task.get('outboundInland') else []
    # main routing
    leg_list += [schema_response.LEG_ADAPTER.dump_python({
        'pointFrom': {'locationName': legs['loadPort'],
                      'locationCode': legs['loadPortCode'],
                      'terminalName': first_pol_terminal_name if legs['vesselSequence'] == 1 else first_pot_terminal_name,
                      'terminalCode': first_pol_terminal_code if legs['vesselSequence'] == 1 else first_pot_terminal_code},
        'pointTo': {'locationName': legs['dischargePort'],
                    'locationCode': legs.get('dischargePortCode') or last_point_to,
                    'terminalName': first_pot_terminal_name if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_name,
                    'terminalCode': first_pot_terminal_code if check_transshipment and legs['vesselSequence'] == 1 else last_pod_terminal_code},
        'etd': etd,
        'eta': (eta := legs.get('vesselArrivalDate')),
        'cutoffs': {'cyCutoffDate': first_cy_cutoff, 'docCutoffDate': first_doc_cutoff} if index == 0 and (first_cy_cutoff or first_doc_cutoff) else None,
        'transitTime': int((datetime.datetime.fromisoformat(eta) - datetime.datetime.fromisoformat(etd)).days),
        'transportations': {'transportType': 'Vessel' if (vessel_name := legs.get('vesselName')) else 'Feeder','transportName': vessel_name,
                            'referenceType': 'IMO' if (imo_code := legs.get('lloydRegisterNo')) else None,
                            'reference': imo_code},
        'services': {'serviceCode': check_service} if (check_service := legs.get('vesselLoop')) else None,
        'voyages': {'internalVoyage': internal_voy if (internal_voy := legs.get('voyageNumber')) else None}},warnings=False) for index, legs in enumerate(schedule_task['vessel']) if (etd := legs.get('vesselDepartureDate'))]
    # inbound
    leg_list += [schema_response.LEG_ADAPTER.dump_python({
        'pointFrom': {'locationName': schedule_task['inboundInland']['fromLocationName'],
                      'locationCode': schedule_task['inboundInland']['fromUnLocationCode'],
                      'terminalName': last_pod_terminal_name,
                      'terminalCode': last_pod_terminal_code},
        'pointTo': {'locationName': schedule_task['inboundInland']['toLocationName'],
                    'locationCode': schedule_task['inboundInland']['toUnLocationCode'],
                    'terminalName': schedule_task['deliveryFacilityName'],
                    'terminalCode': schedule_task['deliveryFaciltyCode']},
        'etd': (inbound_etd := schedule_task['inboundInland']['fromLocationDepatureDate']),
        'eta': (inbound_eta := schedule_task['inboundInland']['toLocationArrivalDate']),
        'transitTime': int((datetime.datetime.fromisoformat(inbound_eta) - datetime.datetime.fromisoformat(inbound_etd)).days),
        'transportations': {'transportType': schedule_task['inboundInland']['transMode']},
        'voyages': {'internalVoyage': 'NA'}}, warnings=False)] if schedule_task.get('inboundInland') else []
    return leg_list


def process_schedule_data(task: dict, vessel_imo: str, service: str, tsp: str) -> Iterator:
    check_service_code: bool = any(services['vesselLoop'] == service for services in task['vessel'] if services.get('vesselDepartureDate')) if service else True
    check_vessel_imo: bool = any(imo for imo in task['vessel'] if imo.get('lloydRegisterNo') == vessel_imo) if vessel_imo else True
    check_transshipment: str|None = task.get('transshipPortCode')
    transshipment_port_filter: bool = bool(check_transshipment == tsp) if check_transshipment and tsp else False
    if (transshipment_port_filter or not tsp) and check_service_code and check_vessel_imo:
        transit_time: int = task.get('totalTransitDay')
        first_pol: str = task.get('loadingPortCode')
        first_point_from: str = task['outboundInland']['fromUnLocationCode'] if task.get('outboundInland') else first_pol
        last_point_to: str = task['inboundInland']['fromUnLocationCode'] if task.get('inboundInland') else task.get('dischargePortCode')
        first_etd: str = task.get('departureDate')
        last_eta: str = task.get('arrivalDate')
        leg_list = process_leg_data(schedule_task=task,last_point_to=last_point_to,check_transshipment=check_transshipment)
        schedule_body: dict = schema_response.SCHEDULE_ADAPTER.dump_python({'scac':'HDMU',
                                                                       'pointFrom':first_point_from,
                                                                       'pointTo':last_point_to, 'etd':first_etd,
                                                                       'eta':last_eta,
                                                                       'transitTime':transit_time,
                                                                       'transshipment':bool(check_transshipment),
                                                                       'legs':leg_list},warnings=False)
        yield schedule_body


async def get_hmm_p2p(client:HTTPClientWrapper, background_task:BackgroundTasks, url: str, pw: str, pol: str, pod: str, search_range: str, direct_only: bool|None,
                      start_date: datetime,tsp: str | None = None,vessel_imo:str | None = None, service: str | None = None) -> Generator:
    params: dict = {'fromLocationCode': pol, 'receiveTermCode': 'CY', 'toLocationCode': pod, 'deliveryTermCode': 'CY',
                    'periodDate': start_date.strftime("%Y%m%d"),'weekTerm': search_range, 'webSort': 'D','webPriority':'D' if direct_only is True else 'T' if direct_only is False else 'A'}
    response_cache = await db.get(scac='hdmu',params=params,original_response=True,log_component='hdmu original response file')
    generate_schedule = lambda data: (schedule_result for task in data.get('resultData') for schedule_result in process_schedule_data(task=task,vessel_imo=vessel_imo,service=service,tsp=tsp))
    if response_cache:
        p2p_schedule:Generator = generate_schedule(data=response_cache)
        return p2p_schedule
    headers: dict = {'x-Gateway-APIKey': pw}
    response_json:dict = await anext(client.parse(scac='hmm',method='POST', url=url, headers=headers,json=params))
    if response_json and response_json.get('resultMessage') == 'Success':
        p2p_schedule:Generator = generate_schedule(data=response_json)
        background_task.add_task(db.set,scac='hdmu',params=params,original_response=True,value=response_json,log_component='hmm original response file')
        return p2p_schedule





