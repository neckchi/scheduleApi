import datetime
import orjson #Orjson is built in RUST, its performing way better than python in built json
import asyncio
from app.carrierp2p.helpers import deepget


#
# async def get_iqax_location_id(client, api_key: str,loc_name:str):
#     url:str = 'https://www.bigschedules.com/openapi/locations/list'
#     params:dict ={'appKey':api_key,'keyword':loc_name}
#     response = await client.get(url=url,params=params)
#     if response.status_code == 200:
#         response_token = json.loads(response.text)
#         loc_id = response_token[0]['locationID']
#         yield loc_id

async def get_multi_iqax_p2p_schedule(client, url: str, params: dict, carrier: str):
    response = await client.get(url=url.format(carrier), params=params)
    yield response

async def get_iqax_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool |None ,
                       tsp: str | None = None, departure_date: str | None = None, arrival_date: str | None = None,
                       scac: str | None = None, service: str | None = None):
    params: dict = {'appKey': pw, 'porID': pol, 'fndID': pod, 'departureFrom': departure_date,
                    'arrivalFrom': arrival_date, 'searchDuration': search_range}
    iqax_list: set = {'OOLU', 'COSU'} if scac is None else {scac}

    async def schedules():
        p2p_resp_tasks: set = {asyncio.create_task(anext(get_multi_iqax_p2p_schedule(client=client, url=url,params= params | {'vesselOperatorCarrierCode': iqax},carrier=iqax))) for iqax in iqax_list}
        # p2p_resp_gather = await asyncio.gather(*p2p_resp_tasks)
        for response in asyncio.as_completed(p2p_resp_tasks):
            response = await response
            if response.status_code == 200:
                response_json:dict = orjson.loads(response.text)
                for schedule_list in response_json['routeGroupsList']:
                    for task in schedule_list['route']:
                        # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                        check_service_code: bool = next((True for services in task['leg'] if services['service']['code'] == service),False) if service else True
                        check_transshipment: bool = False if task['direct'] else True
                        transshipment_port: bool = next((True for tsport in task['leg'][1:] if tsport['fromPoint']['location']['unlocode'] == tsp),False) if check_transshipment and tsp else False
                        if transshipment_port or not tsp:
                            if direct_only is None or (not check_transshipment  and direct_only is True) or (check_transshipment and direct_only is False) :
                                if check_service_code:
                                    carrier_code = task['carrierScac']
                                    transit_time = task['transitTime']
                                    first_point_from = task['por']['location']['unlocode']
                                    last_point_to = task['fnd']['location']['unlocode']
                                    first_etd = task['por']['etd']
                                    last_eta = task['fnd']['eta']
                                    schedule_body: dict = {'scac': carrier_code,
                                                           'pointFrom': first_point_from,
                                                           'pointTo': last_point_to,
                                                           'etd': first_etd,
                                                           'eta': last_eta,
                                                           'transitTime': transit_time,
                                                           'transshipment': check_transshipment
                                                           }

                                    # Performance Enhancement - No meomory is used:async generator object - schedule leg
                                    async def schedule_leg():
                                        for index, legs in enumerate(task['leg'], start=1):
                                            vessel_imo: int | None = legs['vessel'].get('IMO') if legs.get('vessel') else None
                                            vessel_name:str |None  = deepget(legs,'vessel','name')
                                            if index == 1:
                                                final_etd: str = legs['fromPoint'].get('etd', first_etd)
                                                final_eta: str = legs['toPoint'].get('eta', next(ed['fromPoint']['etd'] for ed in task['leg'][1 if transshipment_port else 0::] if ed['fromPoint'].get('etd')))
                                            else:
                                                final_etd: str = legs['fromPoint'].get('etd', next(ea['toPoint']['eta'] for ea in task['leg'][-2::-1] if ea['toPoint'].get('eta')))
                                                final_eta: str = legs['toPoint'].get('eta', last_eta)

                                            leg_transit_time = int((datetime.datetime.fromisoformat(final_eta[:10]) - datetime.datetime.fromisoformat(final_etd[:10])).days)

                                            leg_body: dict = {
                                                'pointFrom': {'locationName': legs['fromPoint']['location']['name'],
                                                              'locationCode': legs['fromPoint']['location']['unlocode'],
                                                              'terminalName': legs['fromPoint']['location']['facility']['name'] if legs['fromPoint']['location'].get('facility') else None,
                                                              'terminalCode': legs['fromPoint']['location']['facility']['code'] if legs['fromPoint']['location'].get('facility') else None
                                                              },
                                                'pointTo': {'locationName': legs['toPoint']['location']['name'],
                                                            'locationCode': legs['toPoint']['location']['unlocode'],
                                                            'terminalName': legs['toPoint']['location']['facility']['name'] if legs['toPoint']['location'].get('facility') else None,
                                                            'terminalCode': legs['toPoint']['location']['facility']['code'] if legs['toPoint']['location'].get('facility') else None
                                                            },
                                                'etd': final_etd,
                                                'eta': final_eta,
                                                'transitTime': legs['transitTime'] if legs.get('transitTime') else leg_transit_time,
                                                'transportations': {
                                                    'transportType': str(legs['transportMode']).title(),
                                                    'transportName': legs['vessel']['name'] if vessel_imo and vessel_name != '---' else None,
                                                    'referenceType': 'IMO' if vessel_imo and vessel_imo != 9999999 else None,
                                                    'reference': None if vessel_imo == 9999999 else vessel_imo
                                                                    }
                                                            }
                                            if legs.get('service'):
                                                service_body: dict = {'serviceCode': legs['service']['code'],'serviceName': legs['service']['name']}
                                                leg_body.update({'services': service_body})

                                            if legs.get('internalVoyageNumber'):
                                                voyage_body: dict = {'internalVoyage': legs['internalVoyageNumber'],
                                                                     'externalVoyage': legs['externalVoyageNumber']}
                                                leg_body.update({'voyages': voyage_body})

                                            if legs['fromPoint'].get('defaultCutoff'):
                                                cut_off_body: dict = {'cyCuttoff': legs['fromPoint']['defaultCutoff']}
                                                leg_body.update({'cutoffs': cut_off_body})

                                            yield leg_body

                                    schedule_body.update({'legs': [sl async for sl in schedule_leg()]})

                                    yield schedule_body

                                else:
                                    pass
                            else:
                                pass
                else:
                    pass

    yield [s async for s in schedules()]
