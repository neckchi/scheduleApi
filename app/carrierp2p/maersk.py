import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime
from fastapi import BackgroundTasks
from itertools import chain


async def process_response_data(client:HTTPXClientWrapper,cut_off_url:str,cut_off_pw:str,response_data: dict, direct_only:bool |None,vessel_imo: str, service: str, tsp: str) -> list:
    total_schedule_list: list = []
    transport_type: dict = {'BAR': 'Barge', 'BCO': 'Barge', 'FEF': 'Feeder', 'FEO': 'Feeder', 'MVS': 'Vessel','RCO': 'Rail', 'RR': 'Rail', 'TRK': 'Truck', 'VSF': 'Feeder', 'VSL': 'Feeder','VSM': 'Vessel'}
    # BU only want the first leg having cut off date
    get_all_first_leg: list[dict] = [{'country': leg['transportLegs'][0]['facilities']['startLocation']['countryCode'],
                                      'pol': leg['transportLegs'][0]['facilities']['startLocation']['cityName'],'imo': imo, 'voyage': leg['transportLegs'][0]['transport'].get('carrierDepartureVoyageNumber')}
                                     for schedule in response_data for leg in schedule['transportSchedules'] if (imo := deepget(leg['transportLegs'][0]['transport'], 'vessel','vesselIMONumber'))
                                     and imo != '9999999' and leg['transportLegs'][0]['transport'].get('carrierDepartureVoyageNumber')]
    cut_off_leg: list = [asyncio.create_task(anext(get_maersk_cutoff(client=client, url=cut_off_url, headers={'Consumer-Key': cut_off_pw}, country=leg.get('country'),pol=leg.get('pol'), imo=leg.get('imo'), voyage=leg.get('voyage'))))
                         for index, leg in enumerate(get_all_first_leg) if leg not in get_all_first_leg[:index]]
    get_cut_offs = await asyncio.gather(*cut_off_leg)
    merged_dict: dict = {key: value for cutoff in get_cut_offs if cutoff is not None for key, value in cutoff.items()}
    for resp in response_data:
        carrier_code: str = resp['vesselOperatorCarrierCode']
        for task in resp['transportSchedules']:
            check_service_code: bool = any(services['transport']['carrierServiceCode'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceCode')) if service else True
            check_service_name: bool = any(services['transport']['carrierServiceName'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceName')) if service else True
            check_transshipment: bool = len(task['transportLegs']) > 1
            transshipment_port: bool = any(tsport['facilities']['startLocation']['UNLocationCode'] == tsp for tsport in task['transportLegs'][1:]) if check_transshipment and tsp else False
            check_vessel_imo: bool = any(imo for imo in task['transportLegs'] if deepget(imo['transport'], 'vessel','vesselIMONumber') == vessel_imo) if vessel_imo else True
            if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and (check_service_code or check_service_name) and check_vessel_imo:
                transit_time: int = round(int(task['transitTime']) / 1400)
                first_point_from: str = task['facilities']['collectionOrigin']['UNLocationCode']
                last_point_to: str = task['facilities']['deliveryDestination']['UNLocationCode']
                first_etd = task['departureDateTime']
                last_eta = task['arrivalDateTime']
                leg_list: list = [schema_response.Leg.model_construct(
                    pointFrom={'locationName': (pol_name := leg['facilities']['startLocation']['cityName']),
                               'locationCode': leg['facilities']['startLocation']['UNLocationCode'],
                               'terminalName': leg['facilities']['startLocation']['locationName']},
                    pointTo={'locationName': leg['facilities']['endLocation']['cityName'],
                             'locationCode': leg['facilities']['endLocation']['UNLocationCode'],
                             'terminalName': leg['facilities']['endLocation']['locationName']},
                    etd=(etd := leg['departureDateTime']),
                    eta=(eta := leg['arrivalDateTime']),
                    transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                    transportations={'transportType': transport_type.get(leg['transport']['transportMode']),
                                     'transportName': deepget(leg['transport'], 'vessel', 'vesselName'),
                                     'referenceType': 'IMO' if (imo_code := str(deepget(leg['transport'], 'vessel', 'vesselIMONumber'))) and imo_code not in ('9999999', 'None') else None,
                                     'reference': imo_code if imo_code not in ('9999999', 'None', '') else None},
                    services={'serviceCode': service_name} if (service_name := leg['transport'].get('carrierServiceName',leg['transport'].get('carrierServiceCode'))) else None,
                    voyages={'internalVoyage': voyage_num} if (voyage_num := leg['transport'].get('carrierDepartureVoyageNumber')) else None,
                    cutoffs=merged_dict.get(hash(leg['facilities']['startLocation']['countryCode'] + pol_name + imo_code + voyage_num)) if pol_name and imo_code and voyage_num else None).model_dump(warnings=False) for leg in task['transportLegs']]
                schedule_body: dict = schema_response.Schedule.model_construct(scac=carrier_code,
                                                                               pointFrom=first_point_from,
                                                                               pointTo=last_point_to, etd=first_etd,
                                                                               eta=last_eta, transitTime=transit_time,
                                                                               transshipment=check_transshipment,
                                                                               legs=sorted(leg_list, key=lambda d: d['etd']) if check_transshipment else leg_list).model_dump(warnings=False)
                total_schedule_list.append(schedule_body)
    return total_schedule_list

async def get_maersk_cutoff(client:HTTPXClientWrapper, url: str, headers: dict, country: str, pol: str, imo: str, voyage: str):
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    async for response_json in client.parse(url=url,method ='GET',stream=True,headers=headers, params=params):
        if response_json:
            lookup_key = hash(country+pol+imo+voyage)
            cut_off_body: dict = {}
            for cutoff in response_json[0]['shipmentDeadlines']['deadlines']:
                if cutoff.get('deadlineName') == 'Commercial Cargo Cutoff':
                    cut_off_body.update({'cyCutoffDate': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') in ('Shipping Instructions Deadline','Shipping Instructions Deadline for Advance Manifest Cargo','Special Cargo Documentation Deadline'):
                    cut_off_body.update({'docCutoffDate': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') == 'Commercial Verified Gross Mass Deadline':
                    cut_off_body.update({'vgmCutoffDate': cutoff.get('deadlineLocal')})
            yield {lookup_key: cut_off_body}
        yield None

async def retrieve_geo_locations(client:HTTPXClientWrapper, background_task:BackgroundTasks, pol:str, pod:str, location_url:str, pw:str):
    maersk_uuid = lambda port: uuid5(NAMESPACE_DNS, f'maersk-loc-uuid-kuehne-nagel-{port}')
    port_uuid:list = [maersk_uuid(port=port) for port in [pol, pod]]
    [origingeolocation, destinationgeolocation] = await asyncio.gather(*(db.get(key=port_id) for port_id in port_uuid))
    if not origingeolocation or not destinationgeolocation:
        port_loading, port_discharge = pol if not origingeolocation else None, pod if not destinationgeolocation else None
        location_tasks = (asyncio.create_task(anext(client.parse(background_tasks=background_task,method='GET',
                        stream=True,url=location_url,headers={'Consumer-Key': pw},params={'locationType': 'CITY', 'UNLocationCode': port},token_key=maersk_uuid(port=port),
                        expire=timedelta(days=360)))) for port in [port_loading, port_discharge] if port)
        location = await asyncio.gather(*location_tasks)
        if origingeolocation is None and destinationgeolocation is None:
            origingeolocation, destinationgeolocation = location
        else:
            origingeolocation, destinationgeolocation = (location[0] if origingeolocation is None else origingeolocation,location[0] if destinationgeolocation is None else destinationgeolocation)
    return origingeolocation, destinationgeolocation

async def get_maersk_p2p(client:HTTPXClientWrapper,background_task:BackgroundTasks,url: str, location_url: str, cutoff_url: str, pw: str, pw2: str, pol: str, pod: str,
                         search_range: str, direct_only: bool|None = None, tsp: str | None = None, scac: str | None = None,start_date: datetime.date = None,date_type: str | None = None, service: str | None = None, vessel_imo:str|None = None,vessel_flag: str | None = None):
    origin_geo_location, des_geo_location = await retrieve_geo_locations(client=client,background_task=background_task,pol=pol,pod=pod,location_url=location_url,pw=pw)
    if origin_geo_location and des_geo_location:
        params:dict= {'collectionOriginCountryCode': origin_geo_location[0]['countryCode'],'collectionOriginCityName': origin_geo_location[0]['cityName'],'collectionOriginUNLocationCode': origin_geo_location[0]['UNLocationCode'],
                        'deliveryDestinationCountryCode': des_geo_location[0]['countryCode'],'deliveryDestinationCityName': des_geo_location[0]['cityName'],'deliveryDestinationUNLocationCode': des_geo_location[0]['UNLocationCode'],
                        'dateRange': f'P{search_range}W', 'startDateType': date_type, 'startDate': start_date}
        params.update({'vesselFlagCode': vessel_flag}) if vessel_flag else ...
        maersk_list: list = ['MAEU', 'MAEI'] if scac is None else [scac]
        maersk_response_uuid = lambda scac: uuid5(NAMESPACE_DNS,f'{str(params) + str(direct_only) + str(vessel_imo) + str(service) + str(tsp) + str(scac)}')
        response_cache = await asyncio.gather(*(db.get(key=maersk_response_uuid(scac=sub_maersk)) for sub_maersk in maersk_list))
        check_cache:bool = any(item is None for item in response_cache)
        p2p_resp_tasks:list = [asyncio.create_task(anext(client.parse(background_tasks =background_task,token_key=maersk_response_uuid(scac=mseries),stream = True, method='GET', url=url,params= dict(params, **{'vesselOperatorCarrierCode': mseries}),
                                                                      headers={'Consumer-Key': pw2})))for mseries,cache in zip(maersk_list,response_cache) if cache is None] if check_cache else...
        for response in (chain(asyncio.as_completed(p2p_resp_tasks),[item for item in response_cache if item is not None]) if check_cache else response_cache):
            response_json:dict = await response if check_cache and not isinstance(response, dict) else response
            check_oceanProducts = response_json.get('oceanProducts') if response_json else None
            if check_oceanProducts:
                p2p_schedule: list = await process_response_data(client=client,cut_off_url=cutoff_url,cut_off_pw = pw,response_data=check_oceanProducts, direct_only=direct_only,vessel_imo=vessel_imo, service=service, tsp=tsp)
                return p2p_schedule
