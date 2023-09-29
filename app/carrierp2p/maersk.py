import asyncio
from datetime import datetime
from typing import Generator
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper

async def get_maersk_cutoff(client, url: str, headers: dict, country: str, pol: str, imo: str, voyage: str):
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    async for response_json in HTTPXClientWrapper.call_client(client=client,url=url,method ='GET',stream=True,headers=headers, params=params):
        cut_off_body: dict = {}
        for cutoff in response_json[0]['shipmentDeadlines']['deadlines']:
            if cutoff.get('deadlineName') == 'Commercial Cargo Cutoff':
                cut_off_body.update({'cyCuttoff': cutoff.get('deadlineLocal')})
            if cutoff.get('deadlineName') in ('Shipping Instructions Deadline','Shipping Instructions Deadline for Advance Manifest Cargo','Special Cargo Documentation Deadline'):
                cut_off_body.update({'siCuttoff': cutoff.get('deadlineLocal')})
            if cutoff.get('deadlineName') == 'Commercial Verified Gross Mass Deadline':
                cut_off_body.update({'vgmCutoff': cutoff.get('deadlineLocal')})
        yield cut_off_body

async def get_maersk_p2p(client, url: str, location_url: str, cutoff_url: str, pw: str, pw2: str, pol: str, pod: str,
                         search_range: str, direct_only: bool|None, tsp: str | None = None, scac: str | None = None,
                         start_date: str | None = None,
                         date_type: str | None = None, service: str | None = None, vessel_flag: str | None = None):
    location_tasks:Generator = (asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client,method='GET',stream=True, url=location_url, headers={'Consumer-Key': pw}, params= {'locationType':'CITY','UNLocationCode': port}))) for port in [pol, pod])
    [origingeolocation, destinationgeolocation] = await asyncio.gather(*location_tasks)
    async def schedules():
        if origingeolocation and destinationgeolocation:
            params: dict = {'collectionOriginCountryCode': origingeolocation['countryCode'],
                            'collectionOriginCityName': origingeolocation['cityName'],
                            'collectionOriginUNLocationCode': origingeolocation['UNLocationCode'],
                            'deliveryDestinationCountryCode': destinationgeolocation['countryCode'],
                            'deliveryDestinationCityName': destinationgeolocation['cityName'],
                            'deliveryDestinationUNLocationCode': destinationgeolocation['UNLocationCode'],
                            'dateRange': f'P{search_range}W', 'startDateType': date_type, 'startDate': start_date}
            params.update({'vesselFlagCode': vessel_flag}) if vessel_flag else ...
            maersk_list: set = {'MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI'} if scac is None else {scac}
            p2p_resp_tasks:list = [asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url,params=dict(params, **{'vesselOperatorCarrierCode': mseries}),headers={'Consumer-Key': pw2}))) for mseries in maersk_list]
            # p2p_resp_gather = await asyncio.gather(*p2p_resp_tasks)
            for response in asyncio.as_completed(p2p_resp_tasks):
                response = await response
                # print(f'Using 2nd API key for p2p schedule- {response}')
                if response.status_code == 200:
                    response_json:dict = response.json()
                    for resp in response_json['oceanProducts']:
                        carrier_code:str = resp['vesselOperatorCarrierCode']
                        for task in resp['transportSchedules']:
                            # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                            check_service_code: bool = next((True for services in task['transportLegs'] if
                                                             services['transport'].get('carrierServiceCode') and
                                                             services['transport']['carrierServiceCode'] == service),
                                                            False) if service else True
                            check_service_name: bool = next((True for services in task['transportLegs'] if
                                                             services['transport'].get('carrierServiceName') and
                                                             services['transport']['carrierServiceName'] == service),
                                                            False) if service else True
                            check_transshipment: bool = True if len(task['transportLegs']) > 1 else False
                            transshipment_port: bool = next((True for tsport in task['transportLegs'][1:] if tsport['facilities']['startLocation']['UNLocationCode'] == tsp),False) if check_transshipment and tsp else False
                            if transshipment_port or not tsp:
                                if direct_only is None or (not check_transshipment and direct_only is True) or (check_transshipment and direct_only is False):
                                    if check_service_code or check_service_name:
                                        transit_time = round(int(task['transitTime']) / 1400)
                                        first_point_from = task['facilities']['collectionOrigin']['UNLocationCode']
                                        last_point_to = task['facilities']['deliveryDestination']['UNLocationCode']
                                        first_etd = task['departureDateTime']
                                        last_eta = task['arrivalDateTime']
                                        schedule_body: dict = {'scac': carrier_code,
                                                               'pointFrom': first_point_from,
                                                               'pointTo': last_point_to, 'etd': first_etd,
                                                               'eta': last_eta,
                                                               'transitTime': transit_time,
                                                               'transshipment': check_transshipment}

                                        # Performance Enhancement - No meomory is used:async generator object - schedule leg
                                        async def schedule_leg():
                                            for index, legs in enumerate(task['transportLegs'], start=1):
                                                vessel_imo:str = deepget(legs['transport'], 'vessel', 'vesselIMONumber')
                                                transport_type: dict = {'BAR': 'Barge',
                                                                        'BCO': 'Barge',
                                                                        'FEF': 'Feeder',
                                                                        'FEO': 'Feeder',
                                                                        'MVS': 'Vessel', 'RCO': 'Rail', 'RR': 'Rail',
                                                                        'TRK': 'Truck',
                                                                        'VSF': 'Feeder',
                                                                        'VSL': 'Feeder',
                                                                        'VSM': 'Vessel'
                                                                        }
                                                leg_body: dict = {
                                                    'pointFrom': {
                                                        'locationName': legs['facilities']['startLocation']['cityName'],
                                                        'locationCode': legs['facilities']['startLocation']['UNLocationCode'],
                                                        'terminalName': legs['facilities']['startLocation']['locationName']
                                                                },
                                                    'pointTo': {
                                                        'locationName': legs['facilities']['endLocation']['cityName'],
                                                        'locationCode': legs['facilities']['endLocation']['UNLocationCode'],
                                                        'terminalName': legs['facilities']['endLocation']['locationName']
                                                                },
                                                    'etd': legs['departureDateTime'],
                                                    'eta': legs['arrivalDateTime'],
                                                    'transitTime': int((datetime.fromisoformat(legs['arrivalDateTime']) - datetime.fromisoformat(legs['departureDateTime'])).days),
                                                    'transportations': {
                                                        'transportType': transport_type.get(legs['transport']['transportMode']),
                                                        'transportName': deepget(legs['transport'], 'vessel','vesselName'),
                                                        'referenceType': 'IMO' if transport_type.get(legs['transport']['transportMode'], 'UNKNOWN') in ('Vessel', 'Feeder','Barge') and vessel_imo else None,
                                                        'reference': vessel_imo
                                                                        }
                                                                }
                                                voyage_num:str = legs['transport'].get('carrierDepartureVoyageNumber')
                                                if voyage_num:
                                                    voyage_body: dict = {'internalVoyage': voyage_num}
                                                    leg_body.update({'voyages': voyage_body})

                                                service_code:str = legs['transport'].get('carrierServiceCode')
                                                service_name:str = legs['transport'].get('carrierServiceName')

                                                if service_code or service_name:
                                                    service_body: dict = {'serviceCode': service_code,'serviceName': service_name}
                                                    leg_body.update({'services': service_body})

                                                # BU only need the cut off date for 1st leg
                                                if index == 1 and vessel_imo and voyage_num:
                                                    cutoffseries = await anext(get_maersk_cutoff(client=client, url=cutoff_url,
                                                                          headers={'Consumer-Key': pw},
                                                                          country=legs['facilities']['startLocation']['countryCode'],
                                                                          pol=legs['facilities']['startLocation']['cityName'],
                                                                          imo=legs['transport']['vessel']['vesselIMONumber'],
                                                                          voyage=voyage_num))
                                                    if cutoffseries:
                                                        leg_body.update({'cutoffs': cutoffseries})

                                                yield leg_body

                                        schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
                                        # Maersk API known issue - sometime they mess up the leg sequence
                                        schedule_body['legs'].sort(key=lambda l: l['etd']) if check_transshipment else ...
                                        yield schedule_body
                                    else:
                                        pass
                                else:
                                    pass
                            else:
                                pass
        else:
            pass
    yield [s async for s in schedules()]
