from datetime import datetime, date
from typing import Generator, Iterator, Optional

from fastapi import BackgroundTasks

from app.api.carrier_api.helpers import deepget
from app.api.schemas.schema_request import SearchRange, StartDateType
from app.api.schemas.schema_response import Cutoff, Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.internal.setting import Settings

DEFAULT_ETD_ETA = datetime.now().astimezone().replace(microsecond=0).isoformat()

CMA_GROUP: dict = {'0001': 'CMDU', '0002': 'ANNU', '0011': 'CHNL', '0015': 'APLU'}


def extract_transportation(transportation: dict):
    """Map the transportation Details"""
    mean_of_transport: str = '/'.join(
        part.strip() for part in str(transportation['meanOfTransport']).title().split('/'))
    vehicule: dict = transportation.get('vehicule', {})
    vessel_imo: str = vehicule.get('reference')
    vehicule_type: str = vehicule.get('vehiculeType')
    reference_type: str | None = None
    reference: str | None = None
    if vessel_imo and len(vessel_imo) < 9:
        reference_type: str = 'IMO'
        reference: str = vessel_imo
    elif vehicule_type == 'Barge':
        reference_type: str = 'IMO'
        reference: str = '9'
    return Transportation.model_construct(transportType=mean_of_transport, transportName=vehicule.get('vehiculeName'),
                                          referenceType=reference_type, reference=reference)


def process_leg_data(leg_task: list) -> list:
    leg_list: list = [
        Leg.model_construct(pointFrom=PointBase.model_construct(locationName=leg['pointFrom']['location']['name'],
                                                                locationCode=leg['pointFrom']['location'].get(
                                                                    'internalCode') or leg['pointFrom']['location'][
            'locationCodifications'][0][
            'codification'],
            terminalName=deepget(leg['pointFrom']['location'],
                                 'facility', 'name'),
            terminalCode=check_pol_terminal[0].get(
                                                                    'codification') if (check_pol_terminal := deepget(
                                                                        leg['pointFrom']['location'], 'facility',
                                                                        'facilityCodifications')) else None),
            pointTo=PointBase.model_construct(locationName=leg['pointTo']['location']['name'],
                                              locationCode=leg['pointTo']['location'].get(
                'internalCode') or leg['pointTo']['location'][
                'locationCodifications'][0][
                'codification'],
            terminalName=deepget(leg['pointTo']['location'],
                                 'facility', 'name'),
            terminalCode=check_pod_terminal[0].get(
                'codification') if (check_pod_terminal := deepget(
                    leg['pointTo']['location'], 'facility',
                    'facilityCodifications')) else None),
            etd=leg['pointFrom'].get('departureDateGmt', DEFAULT_ETD_ETA),
            eta=leg['pointTo'].get('arrivalDateGmt', DEFAULT_ETD_ETA),
            transitTime=leg.get('legTransitTime', 0),
            transportations=extract_transportation(leg['transportation']),
            services=Service.model_construct(serviceCode=service_name) if (
            service_name := deepget(leg['transportation'], 'voyage', 'service', 'code')) else None,
            voyages=Voyage.model_construct(internalVoyage=voyage_num if (
                voyage_num := deepget(leg['transportation'], 'voyage', 'voyageReference')) else None),
            cutoffs=Cutoff.model_construct(
            docCutoffDate=deepget(leg['pointFrom']['cutOff'], 'shippingInstructionAcceptance',
                                  'utc'),
            cyCutoffDate=deepget(leg['pointFrom']['cutOff'], 'portCutoff', 'utc'),
            vgmCutoffDate=deepget(leg['pointFrom']['cutOff'], 'vgm', 'utc')) if leg[
            'pointFrom'].get('cutOff') else None) for leg in leg_task]
    return leg_list


def process_schedule_data(task: dict, direct_only: bool | None, service_filter: str | None,
                          vessel_imo_filter: str | None) -> Iterator:
    """Map the schedule and leg body"""
    transit_time: int = task['transitTime']
    first_point_from: str = task['routingDetails'][0]['pointFrom']['location'].get('internalCode') or \
        task['routingDetails'][0]['pointFrom']['location']['locationCodifications'][0][
        'codification']
    last_point_to: str = task['routingDetails'][-1]['pointTo']['location'].get('internalCode') or \
        task['routingDetails'][-1]['pointTo']['location']['locationCodifications'][0]['codification']
    first_etd = next((ed['pointFrom']['departureDateGmt'] for ed in task['routingDetails'] if
                      ed['pointFrom'].get('departureDateGmt')), DEFAULT_ETD_ETA)
    last_eta = next(
        (ea['pointTo']['arrivalDateGmt'] for ea in task['routingDetails'][::-1] if ea['pointTo'].get('arrivalDateGmt')),
        DEFAULT_ETD_ETA)
    check_transshipment: bool = len(task['routingDetails']) > 1
    check_service_code: bool = any(leg for leg in task['routingDetails'] if
                                   deepget(leg['transportation'], 'voyage', 'service',
                                           'code') == service_filter) if service_filter else True
    check_vessel_imo: bool = any(leg for leg in task['routingDetails'] if deepget(leg['transportation'], 'vehicule',
                                                                                  'reference') == vessel_imo_filter) if vessel_imo_filter else True
    if (direct_only is None or direct_only != check_transshipment) and check_vessel_imo and check_service_code:
        schedule_body = Schedule.model_construct(scac=CMA_GROUP.get(task['shippingCompany']),
                                                 pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=first_etd, eta=last_eta,
                                                 transitTime=transit_time, transshipment=check_transshipment,
                                                 legs=process_leg_data(leg_task=task['routingDetails']))
        yield schedule_body


async def fetch_schedules(client: HTTPClientWrapper, background_task: BackgroundTasks, cma_code: str, url: str,
                          headers: dict, params: dict, extra_condition: bool) -> dict:
    """Fetch the initial set of schedules from CMA."""

    def updated_params(cma_internal_code: str) -> dict:
        """Update request parameters based on CMA internal code and extra condition."""
        updated = {**params}
        if cma_internal_code is not None:
            updated['shippingCompany'] = cma_internal_code
        updated[
            'specificRoutings'] = 'USGovernment' if cma_internal_code == '0015' and extra_condition else 'Commercial'
        return updated

    # Use the updated parameters to fetch the schedules
    response_json: dict = await anext(
        client.parse(
            background_tasks=background_task,
            method='GET',
            url=url,
            params=updated_params(cma_code),
            headers=headers,
            namespace=f'{CMA_GROUP.get(cma_code) if cma_code else "CMDU"} original response'
        )
    )

    if response_json:
        return response_json


async def get_cma_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, api_settings: Settings, pol: str,
                      pod: str, search_range: SearchRange, direct_only: Optional[bool] = None,
                      tsp: Optional[str] = None,
                      vessel_imo: Optional[str] = None,
                      departure_date: Optional[date] = None, arrival_date: Optional[date] = None,
                      start_date_type: Optional[StartDateType] = None,
                      scac: Optional[str] = None,
                      service: Optional[str] = None) -> Generator:
    api_carrier_code: str = next(k for k, v in CMA_GROUP.items() if v == scac.upper()) if scac else None
    headers: dict = {'keyID': api_settings.cma_token.get_secret_value()}
    carrier_params: dict = {'placeOfLoading': pol, 'placeOfDischarge': pod, 'departureDate': departure_date,
                            'searchRange': search_range.duration, 'arrivalDate': arrival_date, 'tsPortCode': tsp}
    params: dict = {k: str(v) for k, v in carrier_params.items() if
                    v is not None}  # Remove the key if its value is None
    extra_condition: bool = pol.startswith('US') and pod.startswith('US')
    response_json = await fetch_schedules(client=client, background_task=background_task, url=api_settings.cma_url,
                                          headers=headers,
                                          params=params, cma_code=api_carrier_code, extra_condition=extra_condition)
    if response_json:
        return (
            schedule_result
            for task in response_json
            for schedule_result in process_schedule_data(
                task=task,
                direct_only=direct_only,
                service_filter=service,
                vessel_imo_filter=vessel_imo,
            ))
