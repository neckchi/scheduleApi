from datetime import datetime, timedelta
from typing import Generator, Iterator, Optional

from fastapi import BackgroundTasks

from app.api.carrier_api.helpers import deepget
from app.api.schemas.schema_request import SearchRange, StartDateType
from app.api.schemas.schema_response import Cutoff, Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.internal.setting import Settings


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
        leg_pol: str = legs['fromPoint']['location']['unlocode']
        leg_pod: str = legs['toPoint']['location']['unlocode']
        if leg_pol != leg_pod:
            imo_code: int | None = legs['vessel'].get('IMO') if legs.get('vessel') else None
            vessel_name: str | None = deepget(legs, 'vessel', 'name')
            check_service = legs.get('service')
            leg_transport: str = legs['transportMode']
            leg_tt: int = legs.get('transitTime')
            leg_etd: str = legs['fromPoint'].get('etd', first_etd)
            tbn_feeder: bool = imo_code is None and vessel_name == 'TBA' and leg_transport.title() == 'Feeder'
            dummy_vehicle: bool = (not tbn_feeder and imo_code is None) or (imo_code and imo_code == 9999999)
            final_etd, final_eta = calculate_final_times(index=index, leg_etd=leg_etd, leg_tt=leg_tt,
                                                         leg_transport=leg_transport, leg_from=legs['fromPoint'],
                                                         legs_to=legs['toPoint'], last_eta=last_eta)
            leg_transit_time: int = leg_tt if leg_tt else (
                datetime.fromisoformat(final_eta[:10]) - datetime.fromisoformat(final_etd[:10])).days
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
                                                               transportName=vessel_name if vessel_name and vessel_name != '---' else 'TBA',
                                                               referenceType={tbn_feeder: 'IMO',
                                                                              dummy_vehicle: None}.get(True, 'IMO'),
                                                               reference={tbn_feeder: '1', dummy_vehicle: None}.get(
                                                                   True, str(imo_code))),
                services=Service.model_construct(serviceCode=legs['service']['code'],
                                                 serviceName=legs['service']['name']) if check_service else None,
                voyages=Voyage.model_construct(
                    internalVoyage=internal_voyage if (internal_voyage := legs.get('internalVoyageNumber')) else None,
                    externalVoyage=legs.get('externalVoyageNumber')),
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


async def get_iqax_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, api_settings: Settings,
                       pol: str,
                       pod: str,
                       search_range: SearchRange,
                       departure_date: Optional[datetime.date] = None,
                       arrival_date: Optional[datetime.date] = None,
                       start_date_type: Optional[StartDateType] = None,
                       direct_only: Optional[bool] = None,
                       tsp: Optional[str] = None,
                       vessel_imo: Optional[str] = None,
                       scac: Optional[str] = None,
                       service: Optional[str] = None) -> Generator:
    carrier_params: dict = {'appKey': api_settings.iqax_token.get_secret_value(),
                            'porID': pol, 'fndID': pod, 'departureFrom': departure_date,
                            'arrivalFrom': arrival_date, 'searchDuration': search_range.value}
    params: dict = {k: str(v) for k, v in carrier_params.items() if v is not None}
    response_json: dict = await anext(
        client.parse(method='GET', background_tasks=background_task, url=api_settings.iqax_url.format(scac),
                     params=params,
                     namespace=f'{scac} original response'))
    if schedule_data := response_json.get('routeGroupsList'):
        return (schedule_result for schedule_list in schedule_data for task in schedule_list['route'] for
                schedule_result in
                process_schedule_data(task=task, direct_only=direct_only, vessel_imo=vessel_imo, service=service,
                                      tsp=tsp))
