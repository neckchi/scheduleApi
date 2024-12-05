from datetime import datetime, timedelta
from typing import Iterator

from fastapi import BackgroundTasks

from app.api.schemas.schema_response import Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper


def process_leg_data(leg_task: list) -> list:
    leg_list: list = [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=leg['departure']['location']['locationName'],
                                            locationCode=leg['departure']['location']['UNLocationCode'],
                                            terminalCode=leg['departure']['location'].get('facilitySMDGCode')),
        pointTo=PointBase.model_construct(locationName=leg['arrival']['location']['locationName'],
                                          locationCode=leg['arrival']['location']['UNLocationCode'],
                                          terminalCode=leg['arrival']['location'].get('facilitySMDGCode')),
        etd=(etd := leg['departure']['dateTime']),
        eta=(eta := leg['arrival']['dateTime']),
        transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
        transportations=Transportation.model_construct(transportType=str(leg.get('modeOfTransport', 'Vessel')).title(),
                                                       transportName=leg['vesselName'] if (
                                                           vessel_imo := leg.get('vesselIMONumber')) else None,
                                                       referenceType='IMO' if vessel_imo and vessel_imo != '0000000' else None,
                                                       reference=vessel_imo if vessel_imo and vessel_imo != '0000000' else None),
        services=Service.model_construct(serviceCode=check_service_code, serviceName=leg.get('carrierServiceName')) if (
            check_service_code := leg.get('carrierServiceCode')) else None,
        voyages=Voyage.model_construct(
            internalVoyage=internal_voy if (internal_voy := leg.get('universalExportVoyageReference')) else None)) for
        leg in leg_task]
    return leg_list


def process_schedule_data(task: dict, service: str, tsp: str, vessel_imo: str) -> Iterator:
    first_point_from: str = task['placeOfReceipt']['location']['UNLocationCode']
    last_point_to: str = task['placeOfDelivery']['location']['UNLocationCode']
    first_etd: datetime = task['placeOfReceipt']['dateTime']
    last_eta: datetime = task['placeOfDelivery']['dateTime']
    transit_time: int = task.get('transitTime',
                                 (datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
    check_service_code: bool = any(
        loop_code for loop_code in task['legs'] if loop_code.get('carrierServiceCode') == service) if service else True
    check_transshipment: bool = len(task['legs']) > 1
    check_vessel_imo: bool = any(
        imo for imo in task['legs'] if imo.get('vesselIMONumber') == vessel_imo) if vessel_imo else True
    transshipment_port: bool = any(tsport['departure']['location']['UNLocationCode'] == tsp for tsport in
                                   task['legs']) if check_transshipment and tsp else False
    if (transshipment_port or not tsp) and (check_service_code or not service) and check_vessel_imo:
        schedule_body = Schedule.model_construct(scac='HLCU', pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=first_etd,
                                                 eta=last_eta, transitTime=transit_time,
                                                 transshipment=check_transshipment,
                                                 legs=process_leg_data(leg_task=task['legs']))
        yield schedule_body


async def get_hlag_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, url: str, client_id: str,
                       client_secret: str, pol: str, pod: str, search_range: int,
                       etd: datetime.date = None, eta: datetime.date = None, direct_only: bool | None = None,
                       service: str | None = None, tsp: str | None = None, vessel_imo: str | None = None):
    start_day: str = etd.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else eta.strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day: str = (etd + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (
            eta + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'departureDateTime:gte': start_day, 'departureDateTime:lte': end_day}) if etd else params.update(
        {'arrivalDateTime:gte': start_day, 'arrivalDateTime:lte': end_day})
    params.update({'isTranshipment': not (direct_only)}) if direct_only is not None else ...
    generate_schedule = lambda data: (result for task in data for result in
                                      process_schedule_data(task=task, service=service, tsp=tsp, vessel_imo=vessel_imo))
    headers: dict = {'X-IBM-Client-Id': client_id, 'X-IBM-Client-Secret': client_secret, 'Accept': 'application/json'}
    response_json = await anext(
        client.parse(method='GET', background_tasks=background_task, url=url, params=params, headers=headers,
                     namespace='hlag original response'))
    if response_json:
        return generate_schedule(data=response_json)
