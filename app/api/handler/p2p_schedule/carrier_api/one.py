from datetime import timedelta, date
from typing import Iterator, Optional, Generator

from fastapi import BackgroundTasks

from app.api.schemas.schema_request import SearchRange, StartDateType
from app.api.schemas.schema_response import Cutoff, Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.internal.setting import Settings


def process_leg_data(check_transshipment: bool, first_point_from: str, last_point_to: str, first_etd: str,
                     last_eta: str, transit_time: int, schedule_task: dict) -> list:
    first_origin_terminal: str = schedule_task['originTerminal']
    last_destination_terminal: str = schedule_task['destinationTerminal']
    first_voyage: str = schedule_task['voyageNumber']
    first_vessel_name: str = schedule_task['vesselName']
    first_imo: str = schedule_task['imoNumber']
    first_service_code: str = schedule_task['serviceCode']
    first_service_name: str | None = schedule_task['serviceName'] if schedule_task['serviceName'] != '' else None
    first_cy_cutoff: str | None = schedule_task['terminalCutoff'] if schedule_task['terminalCutoff'] != '' else None
    first_doc_cutoff: str | None = schedule_task['docCutoff'] if schedule_task['docCutoff'] != '' else None
    first_vgm_cutoff: str | None = schedule_task['vgmCutoff'] if schedule_task['vgmCutoff'] != '' else None
    if check_transshipment:
        leg_list: list = [Leg.model_construct(
            pointFrom=PointBase.model_construct(locationCode=leg['departureUnloc'],
                                                terminalName=leg['departureTerminal']),
            pointTo=PointBase.model_construct(locationCode=leg['arrivalUnloc'], terminalName=leg['arrivalTerminal']),
            etd=leg['departureDateEstimated'],
            eta=leg['arrivalDateEstimated'],
            transitTime=round(leg['transitDurationHrsUtc'] / 24),
            cutoffs=Cutoff.model_construct(cyCutoffDate=first_cy_cutoff, docCutoffDate=first_doc_cutoff,
                                           vgmCutOffDate=first_vgm_cutoff) if index == 0 and (first_cy_cutoff or first_doc_cutoff or first_vgm_cutoff) else None,
            transportations=Transportation.model_construct(transportType='Vessel', transportName=leg['transportName'],
                                                           referenceType=None if (transport_type := leg.get('transportID')) == 'UNKNOWN' else 'IMO',
                                                           reference=None if transport_type == 'UNKNOWN' else transport_type),
            services=Service.model_construct(serviceCode=service_code, serviceName=leg['serviceName']) if (
                service_code := leg['serviceCode']) or (leg['serviceName'] and leg['serviceName'] != '') else None,
            voyages=Voyage.model_construct(
                internalVoyage=voyage_num if (voyage_num := leg.get('conveyanceNumber')) else None)) for index, leg in
            enumerate(schedule_task['legs'])]
    else:
        leg_list: list = [Leg.model_construct(
            pointFrom=PointBase.model_construct(locationCode=first_point_from, terminalName=first_origin_terminal),
            pointTo=PointBase.model_construct(locationCode=last_point_to, terminalName=last_destination_terminal),
            etd=first_etd,
            eta=last_eta,
            transitTime=transit_time,
            cutoffs=Cutoff.model_construct(cyCutoffDate=first_cy_cutoff, docCutoffDate=first_doc_cutoff,
                                           vgmCutoffDate=first_vgm_cutoff) if first_cy_cutoff or first_doc_cutoff or first_vgm_cutoff else None,
            transportations=Transportation.model_construct(transportType='Vessel', transportName=first_vessel_name,
                                                           referenceType=None if first_imo == 'UNKNOWN' else 'IMO',
                                                           reference=None if first_imo == 'UNKNOWN' else first_imo),
            services=Service.model_construct(serviceCode=first_service_code,
                                             serviceName=first_service_name) if first_service_code or first_service_name else None,
            voyages=Voyage.model_construct(internalVoyage=first_voyage if first_voyage else None))]
    return leg_list


def process_response_data(task: dict, vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    service_code: str = task['serviceCode']
    service_name: str = task['serviceName']
    check_service: bool = service_code == service or service_name == service if service else True
    check_transshipment: bool = len(task['legs']) > 1
    transshipment_port: bool = any(
        tsport['departureUnloc'] == tsp for tsport in task['legs'][1:]) if check_transshipment and tsp else False
    check_vessel_imo: bool = (task['imoNumber'] == vessel_imo or any(
        imo for imo in task['legs'] if imo.get('transportID') == vessel_imo)) if vessel_imo else True
    if (transshipment_port or not tsp) and check_service and check_vessel_imo:
        carrier_code: str = task['scac']
        transit_time: int = round(task['transitDurationHrsUtc'] / 24)
        first_point_from: str = task['originUnloc']
        last_point_to: str = task['destinationUnloc']
        first_etd: str = task['originDepartureDateEstimated']
        last_eta: str = task['destinationArrivalDateEstimated']
        schedule_body = Schedule.model_construct(scac=carrier_code, pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=first_etd, eta=last_eta,
                                                 transitTime=transit_time, transshipment=check_transshipment,
                                                 legs=process_leg_data(check_transshipment=check_transshipment,
                                                                       schedule_task=task,
                                                                       first_point_from=first_point_from,
                                                                       last_point_to=last_point_to,
                                                                       first_etd=first_etd, last_eta=last_eta,
                                                                       transit_time=transit_time))
        yield schedule_body


async def get_one_access_token(client: HTTPClientWrapper, background_task: BackgroundTasks, token_url: str, auth: str,
                               api_key: str) -> str:
    headers: dict = {'apikey': api_key, 'Authorization': auth, 'Accept': 'application/json'}
    response_token: dict = await anext(
        client.parse(method='POST', background_tasks=background_task, url=token_url, headers=headers,
                     namespace='one token', expire=timedelta(minutes=55)))
    return response_token['access_token']


async def get_one_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, api_settings: Settings,
                      pol: str, pod: str, search_range: SearchRange,
                      direct_only: Optional[bool], start_date_type: StartDateType,
                      scac: Optional[str] = None,
                      departure_date: Optional[date] = None,
                      arrival_date: Optional[date] = None,
                      service: Optional[str] = None, vessel_imo: Optional[str] = None,
                      tsp: Optional[str] = None) -> Generator:
    # Construct request parameters
    params: dict = {
        'originPort': pol,
        'destinationPort': pod,
        'searchDate': str(departure_date or arrival_date),
        'searchDateType': 'BY_DEPARTURE_DATE' if start_date_type == StartDateType.departure else 'BY_ARRIVAL_DATE',
        'weeksOut': search_range.value,
        'directOnly': 'TRUE' if direct_only is True else 'FALSE'
    }

    # Define a function to generate schedule results
    def generate_schedule(data: dict) -> Generator:
        for schedule_type, tasks in data.items():
            for task in tasks:
                yield from process_response_data(task=task, vessel_imo=vessel_imo, service=service, tsp=tsp)

    # Fetch access token
    token: str = await get_one_access_token(
        client=client,
        background_task=background_task,
        token_url=api_settings.oney_turl,
        auth=api_settings.oney_auth.get_secret_value(),
        api_key=api_settings.oney_token.get_secret_value()
    )

    # Construct request headers
    headers: dict = {
        'apikey': api_settings.oney_token.get_secret_value(),
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }

    # Fetch data from the API
    response_json: dict = await anext(
        client.parse(
            method='GET',
            background_tasks=background_task,
            url=api_settings.oney_url,
            params=params,
            headers=headers,
            namespace='one original response'
        )
    )

    # Validate response and return the schedule generator if no errors
    if response_json and response_json.get('errorMessages') is None:
        return generate_schedule(data=response_json)
