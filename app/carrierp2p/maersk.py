import asyncio
import orjson #Orjson is built in RUST, its performing way better than python in built json
from datetime import datetime
from typing import Generator
from app.carrierp2p.helpers import deepget


async def get_maersk_location_code(client, url: str, headers: dict, unloc: str):
    params: dict = {'UNLocationCode': unloc}
    response = await client.get(url=url, headers=headers, params=params)
    if response.status_code == 200:
        response_json = orjson.loads(orjson.dumps(response.text.splitlines()))
        data = next(
            (orjson.loads(geoid)['countryCode'], orjson.loads(geoid)['cityName'], orjson.loads(geoid)['UNLocationCode']) for
            geoid in response_json if geoid)
        yield data
    else:
        yield None


async def get_maersk_cutoff(client, url: str, headers: dict, country: str, pol: str, imo: str, voyage: str):
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    response = await client.get(url=url, headers=headers, params=params)
    if response.status_code == 200:
        response_json = orjson.loads(response.text)
        cut_off_body: dict = {}
        for cutoff in response_json[0]['shipmentDeadlines']['deadlines']:
            if cutoff.get('deadlineName') == 'Commercial Cargo Cutoff':
                cut_off_body.update({'cyCuttoff': cutoff.get('deadlineLocal')})
            if cutoff.get('deadlineName') in ('Shipping Instructions Deadline','Shipping Instructions Deadline for Advance Manifest Cargo'):
                cut_off_body.update({'siCuttoff': cutoff.get('deadlineLocal')})
            if cutoff.get('deadlineName') == 'Commercial Verified Gross Mass Deadline':
                cut_off_body.update({'vgmCutoff': cutoff.get('deadlineLocal')})
        yield cut_off_body
    else:
        yield None


async def get_maersk_multi_p2p_schedule(client, url: str, params: dict, headers: dict):
    response = await client.get(url=url, params=params, headers=headers)
    yield response

async def get_maersk_p2p(client, url: str, location_url: str, cutoff_url: str, pw: str, pw2: str, pol: str, pod: str,
                         search_range: str, direct_only: bool|None, tsp: str | None = None, scac: str | None = None,
                         start_date: str | None = None,
                         date_type: str | None = None, service: str | None = None, vessel_flag: str | None = None):
    location_tasks:Generator = (asyncio.create_task(anext(get_maersk_location_code(client=client, url=location_url, headers={'Consumer-Key': pw}, unloc=port))) for port in [pol, pod])
    [origingeolocation, destinationgeolocation] = await asyncio.gather(*location_tasks)

    async def schedules():
        if origingeolocation and destinationgeolocation:
            params: dict = {'collectionOriginCountryCode': origingeolocation[0],
                            'collectionOriginCityName': origingeolocation[1],
                            'collectionOriginUNLocationCode': origingeolocation[2],
                            'deliveryDestinationCountryCode': destinationgeolocation[0],
                            'deliveryDestinationCityName': destinationgeolocation[1],
                            'deliveryDestinationUNLocationCode': destinationgeolocation[2],
                            'dateRange': f'P{search_range}W', 'startDateType': date_type, 'startDate': start_date}
            params.update({'vesselFlagCode': vessel_flag}) if vessel_flag else ...
            maersk_list: set = {'MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI'} if scac is None else {scac}
            p2p_resp_tasks:list = [asyncio.create_task(anext(get_maersk_multi_p2p_schedule(client=client, url=url,params=dict(params, **{'vesselOperatorCarrierCode': mseries}),
                                                                                            headers={'Consumer-Key': pw2}))) for mseries in maersk_list]
            # p2p_resp_gather = await asyncio.gather(*p2p_resp_tasks)
            for response in asyncio.as_completed(p2p_resp_tasks):
                response = await response
                # print(f'Using 2nd API key for p2p schedule- {response}')
                if response.status_code == 200:
                    response_json = orjson.loads(response.text)
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
                                                vessel_imo = deepget(legs['transport'], 'vessel', 'vesselIMONumber')
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
                                                voyage_num = legs['transport'].get('carrierDepartureVoyageNumber')
                                                if voyage_num:
                                                    voyage_body: dict = {'internalVoyage': voyage_num}
                                                    leg_body.update({'voyages': voyage_body})

                                                if legs['transport'].get('carrierServiceCode'):
                                                    service_body: dict = {'serviceCode': legs['transport'].get('carrierServiceCode'),'serviceName': legs['transport'].get('carrierServiceName')}
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
