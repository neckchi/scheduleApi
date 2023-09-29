from app.routers.router_config import HTTPXClientWrapper
import httpx
import datetime


async def get_zim_access_token(client, url: str, api_key: str, client_id: str, secret: str):
    headers: dict = {'Ocp-Apim-Subscription-Key': api_key,
                     }
    params: dict = {'grant_type': 'client_credentials', 'client_id': client_id,
                    'client_secret': secret, 'scope': 'Vessel Schedule'}
    response = await anext(HTTPXClientWrapper.call_client(client=client,method='POST',url=url, headers=headers, data=params))
    response_token:dict = response.json()
    access_token = response_token['access_token']
    yield access_token


async def get_zim_p2p(client, url: str, turl: str, pw: str, zim_client: str, zim_secret: str, pol: str, pod: str,
                      search_range: int,
                      start_date: str, direct_only: bool |None, service: str | None = None, tsp: str | None = None):
    params: dict = {'originCode': pol, 'destCode': pod, 'fromDate': start_date,'toDate': str(datetime.datetime.strptime(start_date, '%Y-%m-%d') + datetime.timedelta(days=search_range))[:10], 'sortByDepartureOrArrival': 'Departure'}
    while (retries := 3) > 0:
        try:
            token = await anext(get_zim_access_token(client=client, url=turl, api_key=pw, client_id=zim_client, secret=zim_secret))
            headers: dict = {'Ocp-Apim-Subscription-Key': pw, 'Authorization': f'Bearer {token}','Accept': 'application/json'}
            response = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,
                                               headers=headers))

            # # Performance Enhancement - No meomory is used:async generator object - schedules
            async def schedules():
                if response.status_code == 200:
                    response_json:dict = response.json()
                    for task in response_json['response']['routes']:
                        # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                        check_service_code: bool = next((True for services in task['routeLegs'] if services.get('voyage') and services['line'] == service),False) if service else False
                        check_transshipment: bool = True if task['routeLegCount'] > 1 else False
                        transshipment_port: bool = next((True for tsport in task['routeLegs'][1:] if tsport['departurePort'] == tsp),False) if check_transshipment and tsp else False
                        if transshipment_port or not tsp:
                            if direct_only is None or (not check_transshipment  and direct_only is True) or (check_transshipment and direct_only is False):
                                if check_service_code or not service:
                                    carrier_code:str = 'ZIMU'
                                    transit_time:int = task['transitTime']
                                    first_point_from:str = task['departurePort']
                                    last_point_to:str = task['arrivalPort']
                                    first_etd:str = task['departureDate']
                                    last_eta:str = task['arrivalDate']
                                    schedule_body: dict = {'scac': carrier_code, 'pointFrom': first_point_from,
                                                           'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                                           'transitTime': transit_time,
                                                           'transshipment': check_transshipment
                                                           }

                                    # Performance Enhancement - No meomory is used:async generator object - schedule leg
                                    async def schedule_leg():
                                        for legs in task['routeLegs']:
                                            legs: dict
                                            vessel_type:dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel'}
                                            vessel_name: str | None = legs.get('vesselName')
                                            vessel_imo = legs.get('vesselCode')
                                            leg_body:dict = {
                                                        'pointFrom': {'locationCode': legs['departurePort'],
                                                                      'locationName': legs['departurePortName']},
                                                        'pointTo': {'locationCode': legs['arrivalPort'],
                                                                    'locationName': legs['arrivalPortName']},
                                                        'etd': legs['departureDate'],
                                                        'eta': legs['arrivalDate'],
                                                        'transitTime': int((datetime.datetime.fromisoformat(legs['arrivalDate']) - datetime.datetime.fromisoformat(legs['departureDate'])).days),

                                                        'transportations': {
                                                            'transportType': vessel_type.get(legs['vesselName'], 'Vessel'),
                                                            'transportName': None if vessel_name == 'TO BE NAMED' else vessel_name,
                                                            'referenceType': 'Call Sign' if vessel_imo and vessel_name != 'TO BE NAMED' else None,
                                                            'reference': vessel_imo if vessel_name != 'TO BE NAMED' else None}
                                                        }

                                            if legs.get('voyage'):
                                                voyage_body: dict = {'internalVoyage': legs['voyage'] + legs['leg']}
                                                service_body: dict = {'serviceCode': legs['line']}

                                                leg_body.update({'voyages': voyage_body, 'services': service_body})
                                            yield leg_body

                                    schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
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
            break
        except httpx.TimeoutException:
            retries -= 1
        if retries == 0:
            raise PermissionError
        else:yield None

