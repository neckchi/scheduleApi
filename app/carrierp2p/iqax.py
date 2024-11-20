from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPClientWrapper
from app.schemas.schema_response import Schedule, Leg, PointBase, Cutoff, Voyage, Service, Transportation
from app.background_tasks import db
from fastapi import BackgroundTasks
from datetime import datetime, timedelta
from itertools import chain
from typing import Generator, Iterator
import asyncio


def calculate_final_times(index: int, leg_etd: str, leg_tt: int, leg_transport: str, leg_from: dict, legs_to: dict,
                          last_eta: str):
    """Calculate the correct etd eta for each leg """

    def format_datetime(dt):
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    default_offset = timedelta(days=leg_tt if leg_tt else 0.5)
    if index == 1:
        if leg_transport == 'TRUCK':
            final_etd = format_datetime(datetime.strptime(leg_etd, "%Y-%m-%dT%H:%M:%S.000Z") - default_offset)
        else:
            final_etd = leg_etd
        final_eta = legs_to.get('eta', format_datetime(
            datetime.strptime(final_etd, "%Y-%m-%dT%H:%M:%S.000Z") + default_offset))
    else:
        final_eta = legs_to.get('eta', last_eta)
        final_etd = leg_from.get('etd', format_datetime(
            datetime.strptime(final_eta, "%Y-%m-%dT%H:%M:%S.000Z") - default_offset))
    return final_etd, final_eta


def process_leg_data(schedule_task: dict, first_etd: str, last_eta: str) -> list:
    leg_list: list = []
    for index, legs in enumerate(schedule_task['leg'], start=1):
        imo_code: str = str(legs['vessel'].get('IMO')) if legs.get('vessel') else None
        leg_pol: str = legs['fromPoint']['location']['unlocode']
        leg_pod: str = legs['toPoint']['location']['unlocode']
        vessel_name: str | None = deepget(legs, 'vessel', 'name')
        check_service = legs.get('service')
        leg_transport: str = legs['transportMode']
        leg_tt: int = legs.get('transitTime')
        leg_etd: str = legs['fromPoint'].get('etd', first_etd)
        if leg_pol != leg_pod:
            final_etd, final_eta = calculate_final_times(index=index, leg_etd=leg_etd, leg_tt=leg_tt,
                                                         leg_transport=leg_transport, leg_from=legs['fromPoint'],
                                                         legs_to=legs['toPoint'], last_eta=last_eta)
            leg_transit_time: int = leg_tt if leg_tt else (
                (datetime.fromisoformat(final_eta[:10]) - datetime.fromisoformat(final_etd[:10])).days)
            leg_list.append(Leg.model_construct(
                pointFrom=PointBase.model_construct(locationName=legs['fromPoint']['location']['name'],
                                                    locationCode=leg_pol,
                                                    terminalName=legs['fromPoint']['location']['facility']['name'] if (
                                                        check_origin_terminal := legs['fromPoint']['location'].get(
                                                            'facility')) else None,
                                                    terminalCode=legs['fromPoint']['location']['facility'][
                                                        'code'] if check_origin_terminal else None),
                pointTo=PointBase.model_construct(locationName=legs['toPoint']['location']['name'],
                                                  locationCode=leg_pod,
                                                  terminalName=legs['toPoint']['location']['facility']['name'] if (
                                                      check_des_terminal := legs['toPoint']['location'].get(
                                                          'facility')) else None,
                                                  terminalCode=legs['toPoint']['location']['facility'][
                                                      'code'] if check_des_terminal else None),
                etd=final_etd,
                eta=final_eta,
                transitTime=legs.get('transitTime', leg_transit_time),
                transportations=Transportation.model_construct(transportType=leg_transport.title(),
                                                               transportName=legs['vessel'][
                                                                   'name'] if imo_code and vessel_name != '---' else None,
                                                               referenceType='IMO' if imo_code and imo_code not in (
                                                               9999999, '9999999', 'None') else None,
                                                               reference=None if imo_code and imo_code in (
                                                               9999999, '9999999', 'None') else imo_code),
                services=Service.model_construct(serviceCode=legs['service']['code'],
                                                 serviceName=legs['service']['name']) if check_service else None,
                voyages=Voyage.model_construct(
                    internalVoyage=internal_voyage if (internal_voyage := legs.get('internalVoyageNumber')) else None,
                    externalVoyag=legs.get('externalVoyageNumber')),
                cutoffs=Cutoff.model_construct(cyCutoffDate=cy_cutoff) if (cy_cutoff := legs['fromPoint'].get(
                    'defaultCutoff')) and cy_cutoff <= final_etd else None))
    return leg_list


def process_schedule_data(task: dict, direct_only: bool | None, vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    check_service_code: bool = any(service == service_leg['code'] for leg_service in task['leg'] if
                                   (service_leg := leg_service.get('service'))) if service else True
    check_transshipment: bool = not task['direct']
    transshipment_port: bool = any(tsport['fromPoint']['location']['unlocode'] == tsp for tsport in
                                   task['leg'][1:]) if check_transshipment and tsp else False
    check_vessel_imo: bool = any(
        str(imo['vessel'].get('IMO')) == vessel_imo for imo in task['leg'] if imo.get('vessel')) if vessel_imo else True
    if (transshipment_port or not tsp) and (
            direct_only is None or check_transshipment != direct_only) and check_service_code and check_vessel_imo:
        first_etd: str = task['por']['etd']
        last_eta: str = task['fnd']['eta']
        schedule_body = Schedule.model_construct(scac=task.get('carrierScac'),
                                                 pointFrom=task['por']['location']['unlocode'],
                                                 pointTo=task['fnd']['location']['unlocode'],
                                                 etd=first_etd, eta=last_eta, transitTime=task.get('transitTime'),
                                                 transshipment=check_transshipment,
                                                 legs=process_leg_data(schedule_task=task, first_etd=first_etd,
                                                                       last_eta=last_eta))
        yield schedule_body


async def get_iqax_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, url: str, pw: str, pol: str,
                       pod: str, search_range: int, direct_only: bool | None,
                       tsp: str | None = None, departure_date: datetime.date = None, arrival_date: datetime.date = None,
                       vessel_imo: str | None = None, scac: str | None = None, service: str | None = None) -> Generator:
    carrier_params: dict = {'appKey': pw, 'porID': pol, 'fndID': pod, 'departureFrom': departure_date,
                            'arrivalFrom': arrival_date, 'searchDuration': search_range}
    params: dict = {k: v for k, v in carrier_params.items() if v is not None}
    iqax_list: list[str] = ['OOLU', 'COSU'] if scac is None else [scac]
    response_cache: list = await asyncio.gather(
        *(db.get(scac=sub_iqax, params=params, original_response=True, log_component='iqax original response file') for
          sub_iqax in iqax_list))
    check_cache: bool = any(item is None for item in response_cache)
    p2p_resp_tasks: set = {
        asyncio.create_task(anext(client.parse(scac='iqax', method='GET', url=url.format(iqax), params=params))) for
        iqax, cache in zip(iqax_list, response_cache) if cache is None} if check_cache else ...
    combined_p2p_schedule: list = []
    for response in (chain(asyncio.as_completed(p2p_resp_tasks),
                           [item for item in response_cache if item is not None]) if check_cache else response_cache):
        response_json: dict = await response if check_cache and not isinstance(response, dict) else response
        if (check_response := response_json.get('routeGroupsList')):
            combined_p2p_schedule.extend(check_response)
            background_task.add_task(db.set, scac=check_response[0]['carrier']['scac'], params=params,
                                     original_response=True, value=response_json,
                                     log_component='iqax original response file')
    p2p_schedule: Generator = (schedule_result for schedule_list in combined_p2p_schedule for task in
                               schedule_list['route']
                               for schedule_result in
                               process_schedule_data(task=task, direct_only=direct_only, vessel_imo=vessel_imo,
                                                     service=service, tsp=tsp))
    return p2p_schedule
