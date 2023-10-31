import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta,datetime


async def get_maersk_cutoff(client, url: str, headers: dict, country: str, pol: str, imo: str, voyage: str):
    params: dict = {'ISOCountryCode': country, 'portOfLoad': pol, 'vesselIMONumber': imo, 'voyage': voyage}
    async for response_json in HTTPXClientWrapper.call_client(client=client,url=url,method ='GET',stream=True,headers=headers, params=params):
        if response_json:
            cut_off_body: dict = {}
            for cutoff in response_json[0]['shipmentDeadlines']['deadlines']:
                if cutoff.get('deadlineName') == 'Commercial Cargo Cutoff':
                    cut_off_body.update({'cyCutoffDate': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') in ('Shipping Instructions Deadline','Shipping Instructions Deadline for Advance Manifest Cargo','Special Cargo Documentation Deadline'):
                    cut_off_body.update({'siCutoffDate': cutoff.get('deadlineLocal')})
                if cutoff.get('deadlineName') == 'Commercial Verified Gross Mass Deadline':
                    cut_off_body.update({'vgmCutoffDate': cutoff.get('deadlineLocal')})
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
                transport_type: dict = {'BAR': 'Barge', 'BCO': 'Barge', 'FEF': 'Feeder', 'FEO': 'Feeder',
                                        'MVS': 'Vessel', 'RCO': 'Rail', 'RR': 'Rail', 'TRK': 'Truck',
                                        'VSF': 'Feeder', 'VSL': 'Feeder', 'VSM': 'Vessel'}
                for resp in check_oceanProducts:
                    carrier_code: str = resp['vesselOperatorCarrierCode']
                    for task in resp['transportSchedules']:
                        check_service_code:bool = any(services['transport']['carrierServiceCode'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceCode') ) if service else True
                        check_service_name: bool = any(services['transport']['carrierServiceName'] == service for services in task['transportLegs'] if services['transport'].get('carrierServiceName') ) if service else True
                        check_transshipment: bool = len(task['transportLegs']) > 1
                        transshipment_port:bool = any(tsport['facilities']['startLocation']['UNLocationCode'] == tsp  for tsport in task['transportLegs'][1:]) if check_transshipment and tsp else False
                        if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and (check_service_code or check_service_name):
                            transit_time:int = round(int(task['transitTime']) / 1400)
                            first_point_from:str = task['facilities']['collectionOrigin']['UNLocationCode']
                            last_point_to:str = task['facilities']['deliveryDestination']['UNLocationCode']
                            first_etd = task['departureDateTime']
                            last_eta = task['arrivalDateTime']
                            leg_list: list = [schema_response.Leg.model_construct(
                                pointFrom={'locationName': (pol_name:=leg['facilities']['startLocation']['cityName']),
                                           'locationCode': leg['facilities']['startLocation']['UNLocationCode'],
                                           'terminalName': leg['facilities']['startLocation']['locationName']},
                                pointTo={'locationName': leg['facilities']['endLocation']['cityName'],
                                         'locationCode': leg['facilities']['endLocation']['UNLocationCode'],
                                         'terminalName': leg['facilities']['endLocation']['locationName']},
                                etd=(etd:=leg['departureDateTime']),
                                eta=(eta:=leg['arrivalDateTime']),
                                transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                                transportations={'transportType': transport_type.get(leg['transport']['transportMode']),
                                                 'transportName': deepget(leg['transport'], 'vessel', 'vesselName'),
                                                 'referenceType':'IMO' if (vessel_imo := deepget(leg['transport'], 'vessel','vesselIMONumber')) and vessel_imo != '9999999' else None,
                                                 'reference': vessel_imo if vessel_imo != '9999999' else None},
                                services={'serviceCode': service_name } if (service_name:=leg['transport'].get('carrierServiceName',leg['transport'].get('carrierServiceCode'))) else None,
                                voyages={'internalVoyage':voyage_num} if (voyage_num:=leg['transport'].get('carrierDepartureVoyageNumber')) else None,
                                cutoffs = await anext(get_maersk_cutoff(client=client, url=cutoff_url,headers={'Consumer-Key': pw},country=leg['facilities']['startLocation']['countryCode'],pol=pol_name,imo=vessel_imo,voyage=voyage_num))
                                          if  index == 1 and vessel_imo and vessel_imo != '9999999' and voyage_num else None).model_dump(warnings=False) for index, leg in enumerate(task['transportLegs'], start=1)]
                            schedule_body: dict = schema_response.Schedule.model_construct(scac=carrier_code,
                                                                                           pointFrom=first_point_from,
                                                                                           pointTo=last_point_to,
                                                                                           etd=first_etd, eta=last_eta,
                                                                                           transitTime=transit_time,
                                                                                           transshipment=check_transshipment,
                                                                                           legs=sorted(leg_list,key=lambda d: d['etd']) if check_transshipment else leg_list).model_dump(warnings=False)
                            total_schedule_list.append(schedule_body)
                return total_schedule_list
