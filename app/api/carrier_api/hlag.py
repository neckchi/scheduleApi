from datetime import datetime, timedelta
from typing import Iterator, Optional

from fastapi import BackgroundTasks

from app.api.schemas.schema_request import SearchRange, StartDateType
from app.api.schemas.schema_response import Leg, PointBase, Schedule, Service, Transportation, Voyage
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.internal.setting import Settings


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


async def get_hlag_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks,
                       api_settings: Settings,
                       pol: str, pod: str,
                       search_range: SearchRange,
                       start_date_type: Optional[StartDateType] = None,
                       departure_date: Optional[datetime] = None,
                       arrival_date: Optional[datetime] = None,
                       direct_only: Optional[bool] = None,
                       scac: Optional[str] = None,
                       service: Optional[str] = None,
                       tsp: Optional[str] = None,
                       vessel_imo: Optional[str] = None):
    # Determine the start and end day based on ETD or ETA
    start_day: str = departure_date.strftime("%Y-%m-%dT%H:%M:%S.%SZ") if departure_date else arrival_date.strftime(
        "%Y-%m-%dT%H:%M:%S.%SZ")
    end_day: str = (
        (departure_date + timedelta(days=int(search_range.duration))).strftime(
            "%Y-%m-%dT%H:%M:%S.%SZ") if departure_date else
        (arrival_date + timedelta(days=int(search_range.duration))).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    )

    # Construct the request parameters
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    if departure_date:
        params.update({'departureDateTime:gte': start_day, 'departureDateTime:lte': end_day})
    else:
        params.update({'arrivalDateTime:gte': start_day, 'arrivalDateTime:lte': end_day})

    if direct_only is not None:
        params.update({'isTranshipment': not direct_only})

    # Define a function to generate schedules from response data
    def generate_schedule(data):
        for task in data:
            for result in process_schedule_data(task=task, service=service, tsp=tsp, vessel_imo=vessel_imo):
                yield result

    # Construct the request headers
    headers: dict = {
        'X-IBM-Client-Id': api_settings.hlcu_client_id.get_secret_value(),
        'X-IBM-Client-Secret': api_settings.hlcu_client_secret.get_secret_value(),
        'Accept': 'application/json'
    }

    # Fetch data from the API
    response_json = await anext(
        client.parse(
            method='GET',
            background_tasks=background_task,
            url=api_settings.hlcu_url,
            params=params,
            headers=headers,
            namespace='hlag original response'
        )
    )

    # If response data is available, generate the schedule
    if response_json:
        return generate_schedule(data=response_json)
