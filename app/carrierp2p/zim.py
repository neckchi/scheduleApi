from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from app.carrierp2p import mapping_template
import datetime


async def get_zim_access_token(client,background_task, url: str, api_key: str, client_id: str, secret: str):
    zim_token_key = uuid5(NAMESPACE_DNS, 'zim-token-uuid-kuehne-nagel')
    response_token = await db.get(key=zim_token_key)
    if not response_token:
        headers: dict = {'Ocp-Apim-Subscription-Key': api_key,
                         }
        params: dict = {'grant_type': 'client_credentials', 'client_id': client_id,
                        'client_secret': secret, 'scope': 'Vessel Schedule'}
        response_token = await anext(HTTPXClientWrapper.call_client(client=client,background_tasks=background_task,method='POST',url=url, headers=headers, data=params,token_key=zim_token_key,expire=datetime.timedelta(minutes=40)))
    yield response_token['access_token']

async def get_zim_p2p(client, background_task,url: str, turl: str, pw: str, zim_client: str, zim_secret: str, pol: str, pod: str,
                      search_range: int,
                      start_date: datetime.datetime.date, direct_only: bool |None, service: str | None = None, tsp: str | None = None):
    params: dict = {'originCode': pol, 'destCode': pod, 'fromDate': start_date,'toDate': (start_date + datetime.timedelta(days=search_range)).strftime("%Y-%m-%d"), 'sortByDepartureOrArrival': 'Departure'}

    token = await anext(get_zim_access_token(client=client,background_task=background_task, url=turl, api_key=pw, client_id=zim_client, secret=zim_secret))
    headers: dict = {'Ocp-Apim-Subscription-Key': pw, 'Authorization': f'Bearer {token}','Accept': 'application/json'}
    response_json = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,headers=headers))
    if response_json:
        total_schedule_list:list = []
        for task in response_json['response']['routes']:
            # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
            check_service_code:bool = any(service == services['line'] for services in task['routeLegs'] if services.get('voyage')) if service else True
            check_transshipment: bool = task['routeLegCount'] > 1
            transshipment_port:bool = any(tsport['departurePort'] == tsp for tsport in task['routeLegs'][1:]) if check_transshipment and tsp else False
            if (transshipment_port or not tsp) and (direct_only is None or direct_only != check_transshipment )and (check_service_code or not service):
                carrier_code:str = 'ZIMU'
                transit_time:int = task['transitTime']
                first_point_from:str = task['departurePort']
                last_point_to:str = task['arrivalPort']
                first_etd:str = task['departureDate']
                last_eta:str = task['arrivalDate']
                schedule_body: dict = mapping_template.produce_schedule_body(
                    carrier_code=carrier_code,
                    first_point_from=first_point_from,
                    last_point_to=last_point_to,
                    first_etd=first_etd,
                    last_eta=last_eta,
                    transit_time=transit_time,
                    check_transshipment=check_transshipment)
                leg_list: list = []
                for legs in task['routeLegs']:
                    vessel_type:dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel'}
                    vessel_name: str | None = legs.get('vesselName')
                    vessel_imo = legs.get('vesselCode')
                    check_voyage = legs.get('voyage')
                    leg_list.append(mapping_template.produce_leg_body(
                        origin_un_name=legs['departurePortName'],
                        origin_un_code=legs['departurePort'],
                        dest_un_name=legs['arrivalPortName'],
                        dest_un_code=legs['arrivalPort'],
                        etd=legs['departureDate'],
                        eta=legs['arrivalDate'],
                        tt=int((datetime.datetime.fromisoformat(legs['arrivalDate']) - datetime.datetime.fromisoformat(legs['departureDate'])).days),
                        transport_type=vessel_type.get(legs['vesselName'], 'Vessel'),
                        transport_name=None if vessel_name == 'TO BE NAMED' else vessel_name,
                        reference_type='Call Sign' if vessel_imo and vessel_name != 'TO BE NAMED' else None,
                        reference=vessel_imo if vessel_name != 'TO BE NAMED' else None,
                        service_code=legs['line'] if check_voyage else None,
                        internal_voy=check_voyage + legs['leg'] if check_voyage else None))
                total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
        return total_schedule_list


