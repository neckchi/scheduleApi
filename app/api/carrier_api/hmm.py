import datetime
from typing import Generator, Iterator, Optional

from fastapi import BackgroundTasks

from app.api.schemas.schema_response import Cutoff, Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper


def process_leg_data(schedule_task: dict, last_point_to: str, check_transshipment: str | None) -> list:
    first_pol_terminal_name: str = schedule_task.get('loadingTerminalName')
    first_pol_terminal_code: str = schedule_task.get('loadingTerminalCode')
    first_pot_terminal_name: str = schedule_task.get('transshipTerminalName')
    first_pot_terminal_code: str = schedule_task.get('transshipTerminalCode')
    last_pod_terminal_name: str = schedule_task.get('dischargeTerminalName')
    last_pod_terminal_code: str = schedule_task.get('dischargeTerminalCode')
    first_cy_cutoff: str = schedule_task.get('cargoCutOffTime')
    first_doc_cutoff: str = schedule_task.get('docuCutOffTime')
    # outbound
    leg_list: list = [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=schedule_task['outboundInland']['fromLocationName'],
                                            locationCode=schedule_task['outboundInland']['fromUnLocationCode'],
                                            terminalName=schedule_task['porFacilityName'],
                                            terminalCode=schedule_task['porFacilityCode']),
        pointTo=PointBase.model_construct(locationName=schedule_task['outboundInland']['toLocationName'],
                                          locationCode=schedule_task['outboundInland']['toUnLocationCode'],
                                          terminalName=first_pol_terminal_name,
                                          terminalCode=first_pol_terminal_code),
        etd=(outbound_etd := schedule_task['outboundInland']['fromLocationDepatureDate']),
        eta=(outbound_eta := schedule_task['outboundInland']['toLocationArrivalDate']),
        transitTime=int(
            (datetime.datetime.fromisoformat(outbound_eta) - datetime.datetime.fromisoformat(outbound_etd)).days),
        transportations=Transportation.model_construct(transportType=schedule_task['outboundInland']['transMode']),
        voyages=Voyage.model_construct(internalVoyage='001'))] if schedule_task.get('outboundInland') else []
    # main routing
    leg_list += [Leg.model_construct(pointFrom=PointBase.model_construct(locationName=legs['loadPort'],
                                                                         locationCode=legs['loadPortCode'],
                                                                         terminalName=first_pol_terminal_name if legs[
                                                                                                                     'vesselSequence'] == 1 else first_pot_terminal_name,
                                                                         terminalCode=first_pol_terminal_code if legs[
                                                                                                                     'vesselSequence'] == 1 else first_pot_terminal_code),
                                     pointTo=PointBase.model_construct(locationName=legs['dischargePort'],
                                                                       locationCode=legs.get(
                                                                           'dischargePortCode') or last_point_to,
                                                                       terminalName=first_pot_terminal_name if check_transshipment and
                                                                                                               legs[
                                                                                                                   'vesselSequence'] == 1 else last_pod_terminal_name,
                                                                       terminalCode=first_pot_terminal_code if check_transshipment and
                                                                                                               legs[
                                                                                                                   'vesselSequence'] == 1 else last_pod_terminal_code),
                                     etd=etd,
                                     eta=(eta := legs.get('vesselArrivalDate')),
                                     cutoffs=Cutoff.model_construct(cyCutoffDate=first_cy_cutoff,
                                                                    docCutoffDate=first_doc_cutoff) if index == 0 and (
                                       first_cy_cutoff or first_doc_cutoff) else None,
                                     transitTime=int((datetime.datetime.fromisoformat(
                                         eta) - datetime.datetime.fromisoformat(etd)).days),
                                     transportations=Transportation.model_construct(transportType='Vessel' if (
                                         vessel_name := legs.get('vesselName')) else 'Feeder',
                                                                                    transportName=vessel_name,
                                                                                    referenceType='IMO' if (
                                                                                        imo_code := legs.get(
                                                                                            'lloydRegisterNo')) else None,
                                                                                    reference=imo_code),
                                     services=Service.model_construct(serviceCode=check_service) if (
                                         check_service := legs.get('vesselLoop')) else None,
                                     voyages=Voyage.model_construct(internalVoyage=internal_voy if (
                                         internal_voy := legs.get('voyageNumber')) else None)) for index, legs in
                 enumerate(schedule_task['vessel']) if (etd := legs.get('vesselDepartureDate'))]
    # inbound
    leg_list += [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=schedule_task['inboundInland']['fromLocationName'],
                                            locationCode=schedule_task['inboundInland']['fromUnLocationCode'],
                                            terminalName=last_pod_terminal_name,
                                            terminalCode=last_pod_terminal_code),
        pointTo=PointBase.model_construct(locationName=schedule_task['inboundInland']['toLocationName'],
                                          locationCode=schedule_task['inboundInland']['toUnLocationCode'],
                                          terminalName=schedule_task['deliveryFacilityName'],
                                          terminalCode=schedule_task['deliveryFaciltyCode']),
        etd=(inbound_etd := schedule_task['inboundInland']['fromLocationDepatureDate']),
        eta=(inbound_eta := schedule_task['inboundInland']['toLocationArrivalDate']),
        transitTime=int(
            (datetime.datetime.fromisoformat(inbound_eta) - datetime.datetime.fromisoformat(inbound_etd)).days),
        transportations=Transportation.model_construct(transportType=schedule_task['inboundInland']['transMode']),
        voyages=Voyage.model_construct(internalVoyage='001'))] if schedule_task.get('inboundInland') else []
    return leg_list


def process_schedule_data(task: dict, vessel_imo: str, service: str, tsp: str) -> Iterator:
    check_service_code: bool = any(services['vesselLoop'] == service for services in task['vessel'] if
                                   services.get('vesselDepartureDate')) if service else True
    check_vessel_imo: bool = any(
        imo for imo in task['vessel'] if imo.get('lloydRegisterNo') == vessel_imo) if vessel_imo else True
    check_transshipment: str | None = task.get('transshipPortCode')
    transshipment_port_filter: bool = bool(check_transshipment == tsp) if check_transshipment and tsp else False
    if (transshipment_port_filter or not tsp) and check_service_code and check_vessel_imo:
        transit_time: int = task.get('totalTransitDay')
        first_pol: str = task.get('loadingPortCode')
        first_point_from: str = task['outboundInland']['fromUnLocationCode'] if task.get(
            'outboundInland') else first_pol
        last_point_to: str = task['inboundInland']['fromUnLocationCode'] if task.get('inboundInland') else task.get(
            'dischargePortCode')
        first_etd: str = task.get('departureDate')
        last_eta: str = task.get('arrivalDate')
        leg_list = process_leg_data(schedule_task=task, last_point_to=last_point_to,
                                    check_transshipment=check_transshipment)
        schedule_body = Schedule.model_construct(scac='HDMU', pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=first_etd,
                                                 eta=last_eta, transitTime=transit_time,
                                                 transshipment=bool(check_transshipment),
                                                 legs=leg_list)
        yield schedule_body


async def get_hmm_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, url: str, pw: str, pol: str,
                      pod: str, search_range: str, direct_only: Optional[bool],
                      start_date: datetime, tsp: Optional[str] = None, vessel_imo: Optional[str] = None,
                      service: Optional[str] = None) -> Generator:
    # Construct request parameters
    params: dict = {
        'fromLocationCode': pol,
        'receiveTermCode': 'CY',
        'toLocationCode': pod,
        'deliveryTermCode': 'CY',
        'periodDate': start_date.strftime("%Y%m%d"),
        'weekTerm': search_range,
        'webSort': 'D' if direct_only is True else 'T' if direct_only is False else 'A',
        'webPriority': 'D' if direct_only is True else 'T' if direct_only is False else 'A'
    }

    # Define a function to generate schedule results
    def generate_schedule(data: dict) -> Generator:
        for task in data.get('resultData', []):
            for schedule_result in process_schedule_data(task=task, vessel_imo=vessel_imo, service=service, tsp=tsp):
                yield schedule_result

    # Construct request headers
    headers: dict = {'x-Gateway-APIKey': pw}

    # Fetch data from the API
    response_json: dict = await anext(
        client.parse(
            method='POST',
            background_tasks=background_task,
            url=url,
            headers=headers,
            json=params,
            namespace='hmm original response'
        )
    )

    # Validate response and return schedule generator if successful
    if response_json and response_json.get('resultMessage') == 'Success':
        return generate_schedule(data=response_json)
