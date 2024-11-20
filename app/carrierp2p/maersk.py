import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPClientWrapper
from app.background_tasks import db
from app.schemas.schema_response import Schedule, Leg, PointBase, Cutoff, Voyage, Service, Transportation
from uuid import uuid5, NAMESPACE_DNS
from datetime import timedelta, datetime
from fastapi import BackgroundTasks
from itertools import chain
from typing import Generator, Iterator
from app.schemas.schema_request import TRANSPORT_TYPE


def process_leg_data(leg_task: list, first_cut_off: dict):
    leg_list: list = [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=(pol_name := leg['facilities']['startLocation']['cityName']),
                                            locationCode=pol_code,
                                            terminalName=leg['facilities']['startLocation']['locationName']),
        pointTo=PointBase.model_construct(locationName=leg['facilities']['endLocation']['cityName'],
                                          locationCode=pod_code,
                                          terminalName=leg['facilities']['endLocation']['locationName']),
        etd=(etd := leg['departureDateTime']),
        eta=(eta := leg['arrivalDateTime']),
        transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
        transportations=Transportation.model_construct(
            transportType=TRANSPORT_TYPE.get(leg['transport']['transportMode']),
            transportName=deepget(leg['transport'], 'vessel', 'vesselName'),
            referenceType='IMO' if (imo_code := str(
                deepget(leg['transport'], 'vessel', 'vesselIMONumber'))) and imo_code not in (
                '9999999', 'None') else None,
            reference=imo_code if imo_code not in ('9999999', 'None', '') else None),
        services=Service.model_construct(serviceCode=service_name) if (
            service_name := leg['transport'].get('carrierServiceName',
                                                 leg['transport'].get('carrierServiceCode'))) else None,
        voyages=Voyage.model_construct(internalVoyage=voyage_num if (
            voyage_num := leg['transport'].get('carrierDepartureVoyageNumber')) else None),
        cutoffs=first_cut_off.get(hash(leg['facilities']['startLocation'][
            'countryCode'] + pol_name + imo_code + voyage_num)) if pol_name and imo_code and voyage_num else None)
        for leg in leg_task
        if (pol_code := leg['facilities']['startLocation'].get('cityUNLocationCode') or leg['facilities']['startLocation'].get('siteUNLocationCode')) != (pod_code := leg['facilities']['endLocation'].get('cityUNLocationCode') or leg['facilities']['endLocation'].get('siteUNLocationCode'))]
    return leg_list


def process_schedule_data(resp: dict, first_cut_off: dict, direct_only: bool | None, vessel_imo: str, service: str,
                          tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    carrier_code: str = resp['vesselOperatorCarrierCode']
    for task in resp['transportSchedules']:
        check_service_code: bool = any(
            services['transport']['carrierServiceCode'] == service for services in task['transportLegs'] if
            services['transport'].get('carrierServiceCode')) if service else True
        check_service_name: bool = any(
            services['transport']['carrierServiceName'] == service for services in task['transportLegs'] if
            services['transport'].get('carrierServiceName')) if service else True
        check_transshipment: bool = len(task['transportLegs']) > 1
        transshipment_port: bool = any(tsport['facilities']['startLocation']['UNLocationCode'] == tsp for tsport in
                                       task['transportLegs'][1:]) if check_transshipment and tsp else False
        check_vessel_imo: bool = any(imo for imo in task['transportLegs'] if deepget(imo['transport'], 'vessel',
                                                                                     'vesselIMONumber') == vessel_imo) if vessel_imo else True
        if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and (
                check_service_code or check_service_name) and check_vessel_imo:
            transit_time: int = round(int(task['transitTime']) / 1400)
            first_point_from: str = task['facilities']['collectionOrigin'].get('cityUNLocationCode') or \
                task['facilities']['collectionOrigin'].get('siteUNLocationCode')
            last_point_to: str = task['facilities']['deliveryDestination'].get('cityUNLocationCode') or \
                task['facilities']['deliveryDestination'].get('siteUNLocationCode')
            first_etd: str = task['departureDateTime']
            last_eta: str = task['arrivalDateTime']
            leg_list = process_leg_data(leg_task=task['transportLegs'], first_cut_off=first_cut_off)
            schedule_body = Schedule.model_construct(scac=carrier_code, pointFrom=first_point_from,
                                                     pointTo=last_point_to, etd=first_etd, eta=last_eta,
                                                     transitTime=transit_time, transshipment=check_transshipment,
                                                     legs=sorted(leg_list, key=lambda
                                                                 leg: leg.etd) if check_transshipment else leg_list)
            yield schedule_body


async def get_cutoff_first_leg(client: HTTPClientWrapper, cut_off_url: str, cut_off_pw: str,
                               response_data: list) -> dict:
    """According to the BU requirment, we have to get the first leg from Maersk P2P schedule and map the cutOffDate for the first leg only"""
    get_all_first_leg: list[dict] = [{'country': leg['transportLegs'][0]['facilities']['startLocation']['countryCode'],
                                      'pol': leg['transportLegs'][0]['facilities']['startLocation']['cityName'],
                                      'imo': imo, 'voyage': leg['transportLegs'][0]['transport'].get(
        'carrierDepartureVoyageNumber')}
        for schedule in response_data for leg in schedule['transportSchedules'] if
        (imo := deepget(leg['transportLegs'][0]['transport'], 'vessel', 'vesselIMONumber')) and imo != '9999999' and leg['transportLegs'][0]['transport'].get('carrierDepartureVoyageNumber')]
    cut_off_leg: list = [asyncio.create_task(
        get_maersk_cutoff(client=client, url=cut_off_url, headers={'Consumer-Key': cut_off_pw},
                          country=leg.get('country'), pol=leg.get('pol'), imo=leg.get('imo'), voyage=leg.get('voyage')))
                         for index, leg in enumerate(get_all_first_leg) if leg not in get_all_first_leg[:index]]
    get_cut_offs = await asyncio.gather(*cut_off_leg)
    first_cut_off: dict = {key: value for cutoff in get_cut_offs if cutoff is not None for key, value in cutoff.items()}
    return first_cut_off


async def get_maersk_cutoff(client: HTTPClientWrapper, url: str, headers: dict, country: str, pol: str, imo: str,
                            voyage: str) -> dict | None:
    """Fetches the cutoff dates from the Maersk API."""
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    async for response_json in client.parse(scac='maersk', url=url, method='GET', stream=True, headers=headers,
                                            params=params):
        if not response_json:
            return None
        lookup_key = hash(f"{country}{pol}{imo}{voyage}")
        cutoff_dates: dict = {}
        deadline_mappings: dict = {'Commercial Cargo Cutoff': 'cyCutoffDate',
                                   'Shipping Instructions Deadline': 'docCutoffDate',
                                   'Shipping Instructions Deadline for Advance Manifest Cargo': 'docCutoffDate',
                                   'Special Cargo Documentation Deadline': 'docCutoffDate',
                                   'Commercial Verified Gross Mass Deadline': 'vgmCutoffDate'}
        for cutoff in response_json[0].get('shipmentDeadlines', {}).get('deadlines', []):
            deadline_name = cutoff.get('deadlineName')
            if deadline_name in deadline_mappings:
                cutoff_dates[deadline_mappings[deadline_name]] = cutoff.get('deadlineLocal')
        if cutoff_dates:
            return {lookup_key: Cutoff.model_construct(cyCutoffDate=cutoff_dates.get('cyCutoffDate'),
                                                       docCutoffDate=cutoff_dates.get('docCutoffDate'),
                                                       vgmCutoffDate=cutoff_dates.get('vgmCutoffDate'))}
        return None


async def retrieve_geo_locations(client: HTTPClientWrapper, background_task: BackgroundTasks, pol: str, pod: str,
                                 location_url: str, pw: str):
    def maersk_uuid(port):
        return uuid5(NAMESPACE_DNS, f'maersk-loc-uuid-kuehne-nagel-{port}')
    port_uuid: list = [maersk_uuid(port=port) for port in [pol, pod]]
    [origingeolocation, destinationgeolocation] = await asyncio.gather(
        *(db.get(key=port_id, log_component='maersk location code') for port_id in port_uuid))
    if not origingeolocation or not destinationgeolocation:
        port_loading, port_discharge = pol if not origingeolocation else None, pod if not destinationgeolocation else None
        location_tasks = (asyncio.create_task(anext(
            client.parse(scac='maersk', background_tasks=background_task, method='GET', stream=True, url=location_url,
                         headers={'Consumer-Key': pw}, params={'locationType': 'CITY', 'UNLocationCode': port},
                         token_key=maersk_uuid(port=port),
                         expire=timedelta(days=360)))) for port in [port_loading, port_discharge] if port)
        location = await asyncio.gather(*location_tasks)
        if origingeolocation is None and destinationgeolocation is None:
            origingeolocation, destinationgeolocation = location
        else:
            origingeolocation, destinationgeolocation = (
                location[0] if origingeolocation is None else origingeolocation,
                location[0] if destinationgeolocation is None else destinationgeolocation)
    return origingeolocation, destinationgeolocation


async def get_maersk_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, url: str, location_url: str,
                         cutoff_url: str, pw: str, pw2: str, pol: str, pod: str, start_date: datetime.date,
                         search_range: str, direct_only: bool | None = None, tsp: str | None = None,
                         scac: str | None = None, date_type: str | None = None, service: str | None = None,
                         vessel_imo: str | None = None, vessel_flag: str | None = None) -> Generator:
    origin_geo_location, des_geo_location = await retrieve_geo_locations(client=client, background_task=background_task,
                                                                         pol=pol, pod=pod, location_url=location_url,
                                                                         pw=pw)
    if origin_geo_location and des_geo_location:
        params: dict = {'collectionOriginCountryCode': origin_geo_location[0]['countryCode'],
                        'collectionOriginCityName': origin_geo_location[0]['cityName'],
                        'collectionOriginUNLocationCode': origin_geo_location[0]['UNLocationCode'],
                        'deliveryDestinationCountryCode': des_geo_location[0]['countryCode'],
                        'deliveryDestinationCityName': des_geo_location[0]['cityName'],
                        'deliveryDestinationUNLocationCode': des_geo_location[0]['UNLocationCode'],
                        'dateRange': f'P{search_range}W', 'startDateType': date_type,
                        'startDate': start_date.strftime('%Y-%m-%d')}
        params.update({'vesselFlagCode': vessel_flag}) if vessel_flag else ...
        maersk_list: list[str] = ['MAEU', 'MAEI'] if scac is None else [scac]
        response_cache = await asyncio.gather(
            *(db.get(scac=sub_maersk, params=params, original_response=True, log_component='maersk original response')
              for sub_maersk in maersk_list))
        check_cache: bool = any(item is None for item in response_cache)
        p2p_resp_tasks: list = [asyncio.create_task(anext(
            client.parse(scac='maersk', stream=True, method='GET', url=url,
                         params=dict(params, **{'vesselOperatorCarrierCode': mseries}), headers={'Consumer-Key': pw2})))
            for mseries, cache in zip(maersk_list, response_cache) if
            cache is None] if check_cache else ...
        for response in (chain(asyncio.as_completed(p2p_resp_tasks), [item for item in response_cache if
                                                                      item is not None]) if check_cache else response_cache):
            response_json: dict = await response if check_cache and not isinstance(response, dict) else response
            check_oceanProducts = response_json.get('oceanProducts') if response_json else None
            if check_oceanProducts:
                first_cut_off: dict = await get_cutoff_first_leg(client=client, cut_off_url=cutoff_url, cut_off_pw=pw,
                                                                 response_data=check_oceanProducts)
                p2p_schedule: Generator = (schedule_result for task in check_oceanProducts for schedule_result in
                                           process_schedule_data(resp=task, first_cut_off=first_cut_off,
                                                                 direct_only=direct_only, vessel_imo=vessel_imo,
                                                                 service=service, tsp=tsp))
                background_task.add_task(db.set, scac=check_oceanProducts[0]['vesselOperatorCarrierCode'],
                                         params=params, original_response=True, value=response_json,
                                         log_component='maersk original response file')
                return p2p_schedule
