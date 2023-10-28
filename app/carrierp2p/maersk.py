import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime
from app.carrierp2p import mapping_template

async def get_maersk_cutoff(client, url: str, headers: dict, country: str, pol: str, imo: str, voyage: str):
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    async for response_json in HTTPXClientWrapper.call_client(client=client,url=url,method ='GET',stream=True,headers=headers, params=params):
        if response_json:
            cut_off_body: dict = {}
            for cutoff in response_json[0]['shipmentDeadlines']['deadlines']:
                if cutoff.get('deadlineName') == 'Commercial Cargo Cutoff':
                    cut_off_body.update({'cyCuttoff': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') in ('Shipping Instructions Deadline','Shipping Instructions Deadline for Advance Manifest Cargo','Special Cargo Documentation Deadline'):
                    cut_off_body.update({'siCuttoff': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') == 'Commercial Verified Gross Mass Deadline':
                    cut_off_body.update({'vgmCutoff': cutoff.get('deadlineLocal')})
            yield cut_off_body
        yield None


async def get_maersk_p2p(client,background_task,url: str, location_url: str, cutoff_url: str, pw: str, pw2: str, pol: str, pod: str,
                         search_range: str, direct_only: bool|None = None, tsp: str | None = None, scac: str | None = None,
                         start_date: datetime.date = None,
                         date_type: str | None = None, service: str | None = None, vessel_flag: str | None = None):
    maersk_uuid = lambda port:uuid5(NAMESPACE_DNS, f'maersk-loc-uuid-kuehne-nagel-{port}')
    port_uuid:list = [maersk_uuid(port=port) for port in [pol,pod]]
    [origingeolocation,destinationgeolocation] = await asyncio.gather(*(db.get(key=port_id) for port_id in port_uuid))

    if not origingeolocation or not destinationgeolocation:
        port_loading,port_discharge  = pol if not origingeolocation else None, pod if not destinationgeolocation else None
        location_tasks = (asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client,background_tasks=background_task,method='GET',
                                                                                             stream=True, url=location_url, headers={'Consumer-Key': pw},
                                                                                             params= {'locationType':'CITY','UNLocationCode': port},
                                                                                             token_key=maersk_uuid(port=port),expire=timedelta(days=180)))) for port in [port_loading, port_discharge] if port)
        location = await asyncio.gather(*location_tasks)
        if origingeolocation is None and destinationgeolocation is None:
            origingeolocation, destinationgeolocation = location
        else: origingeolocation,destinationgeolocation = location[0] if  origingeolocation is None and destinationgeolocation is not None else origingeolocation,\
            location[0] if destinationgeolocation is None and origingeolocation is not None else destinationgeolocation

    if origingeolocation and destinationgeolocation:
        params: dict = {'collectionOriginCountryCode': origingeolocation[0]['countryCode'],
                        'collectionOriginCityName': origingeolocation[0]['cityName'],
                        'collectionOriginUNLocationCode': origingeolocation[0]['UNLocationCode'],
                        'deliveryDestinationCountryCode': destinationgeolocation[0]['countryCode'],
                        'deliveryDestinationCityName': destinationgeolocation[0]['cityName'],
                        'deliveryDestinationUNLocationCode': destinationgeolocation[0]['UNLocationCode'],
                        'dateRange': f'P{search_range}W', 'startDateType': date_type, 'startDate': start_date}
        params.update({'vesselFlagCode': vessel_flag}) if vessel_flag else ...
        maersk_list: set = {'MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI'} if scac is None else {scac}
        p2p_resp_tasks:list = [asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client,stream = True, method='GET', url=url,params=dict(params, **{'vesselOperatorCarrierCode': mseries}),
                                                                                        headers={'Consumer-Key': pw2}))) for mseries in maersk_list]
        for response in asyncio.as_completed(p2p_resp_tasks):
            response_json = await response
            check_oceanProducts = response_json.get('oceanProducts') if response_json else None
            if check_oceanProducts:
                total_schedule_list: list = []
                for resp in check_oceanProducts:
                    carrier_code:str = resp['vesselOperatorCarrierCode']
                    for task in resp['transportSchedules']:
                        check_service_code:bool = any(services['transport']['carrierServiceCode'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceCode') ) if service else True
                        check_service_name: bool = any(services['transport']['carrierServiceName'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceName') ) if service else True
                        check_transshipment: bool = len(task['transportLegs']) > 1
                        transshipment_port:bool = any(tsport['facilities']['startLocation']['UNLocationCode'] == tsp  for tsport in task['transportLegs'][1:]) if check_transshipment and tsp else False
                        if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and (check_service_code or check_service_name):
                            transit_time:int = round(int(task['transitTime']) / 1400)
                            transport_type: dict = {'BAR': 'Barge', 'BCO': 'Barge', 'FEF': 'Feeder', 'FEO': 'Feeder',
                                                    'MVS': 'Vessel', 'RCO': 'Rail', 'RR': 'Rail', 'TRK': 'Truck',
                                                    'VSF': 'Feeder', 'VSL': 'Feeder', 'VSM': 'Vessel'}
                            first_point_from:str = task['facilities']['collectionOrigin']['UNLocationCode']
                            last_point_to:str = task['facilities']['deliveryDestination']['UNLocationCode']
                            first_etd = task['departureDateTime']
                            last_eta = task['arrivalDateTime']
                            schedule_body: dict = mapping_template.produce_schedule_body(
                                carrier_code=carrier_code,
                                first_point_from=first_point_from,
                                last_point_to=last_point_to,
                                first_etd=first_etd,
                                last_eta=last_eta,
                                transit_time=transit_time,
                                check_transshipment=check_transshipment)
                            leg_list:list = [mapping_template.produce_leg_body(
                                    origin_un_name=(pol_name:=leg['facilities']['startLocation']['cityName']),
                                    origin_un_code=leg['facilities']['startLocation']['UNLocationCode'],
                                    origin_term_name=leg['facilities']['startLocation']['locationName'],
                                    dest_un_name=leg['facilities']['endLocation']['cityName'],
                                    dest_un_code=leg['facilities']['endLocation']['UNLocationCode'],
                                    dest_term_name=leg['facilities']['endLocation']['locationName'],
                                    etd=(etd:=leg['departureDateTime']),
                                    eta=(eta:=leg['arrivalDateTime']),
                                    tt=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                                    transport_type=transport_type.get(leg['transport']['transportMode']),
                                    transport_name=deepget(leg['transport'], 'vessel', 'vesselName'),
                                    reference_type='IMO' if transport_type.get(leg['transport']['transportMode'],'UNKNOWN') in ('Vessel', 'Feeder','Barge')
                                                            and (vessel_imo:=deepget(leg['transport'], 'vessel', 'vesselIMONumber'))
                                                            and vessel_imo != '9999999' else None,
                                    reference=vessel_imo if vessel_imo != '9999999' else None,
                                    service_code=service_name if (service_name:=leg['transport'].get('carrierServiceName')) else leg['transport'].get('carrierServiceCode'),
                                    internal_voy=(voyage_num:=leg['transport'].get('carrierDepartureVoyageNumber')),
                                    cy_cutoff=(cutoffseries:=await anext(get_maersk_cutoff(client=client, url=cutoff_url,headers={'Consumer-Key': pw},country=leg['facilities']['startLocation']['countryCode'],
                                                      pol=pol_name,imo=vessel_imo,voyage=voyage_num))).get('cyCuttoff') if  (first_valid_leg:=index == 1 and vessel_imo and vessel_imo != '9999999' and voyage_num) else None,
                                    si_cutoff=cutoffseries.get('siCuttoff') if  first_valid_leg else None,
                                    vgm_cutoff=cutoffseries.get('vgmCutoff') if  first_valid_leg else None ) for index, leg in enumerate(task['transportLegs'], start=1)]
                            total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
                return total_schedule_list


# # Maersk API known issue - sometime they mess up the leg sequence
# schedule_body['legs'].sort(key=lambda l: l['etd']) if check_transshipment else ...