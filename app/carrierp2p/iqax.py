import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from datetime import datetime,timedelta
from app.carrierp2p import mapping_template

async def get_iqax_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool |None ,
                       tsp: str | None = None, departure_date:datetime.date = None, arrival_date: datetime.date = None,
                       scac: str | None = None, service: str | None = None):
    params: dict = {'appKey': pw, 'porID': pol, 'fndID': pod, 'departureFrom': departure_date,
                    'arrivalFrom': arrival_date, 'searchDuration': search_range}
    iqax_list: set = {'OOLU', 'COSU'} if scac is None else {scac}
    p2p_resp_tasks: set = {asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url.format(iqax),params=dict(params, **{'vesselOperatorCarrierCode': iqax})))) for iqax in iqax_list}
    total_schedule_list: list = []
    for response in asyncio.as_completed(p2p_resp_tasks):
        response_json = await response
        if response_json:
            for schedule_list in response_json['routeGroupsList']:
                for task in schedule_list['route']:
                    check_service_code:bool = any(service == leg_service['service']['code'] for leg_service in task['leg']) if service else True
                    check_transshipment: bool = not task['direct']
                    transshipment_port:bool = any(tsport['fromPoint']['location']['unlocode'] == tsp for tsport in task['leg'][1:]) if check_transshipment and tsp else False
                    if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and check_service_code:
                        first_etd:str = task['por']['etd']
                        last_eta:str = task['fnd']['eta']
                        schedule_body: dict = mapping_template.produce_schedule_body(carrier_code=task.get('carrierScac'),
                                                                                     first_point_from=task['por']['location']['unlocode'],
                                                                                     last_point_to=task['fnd']['location']['unlocode'],
                                                                                     first_etd=first_etd,
                                                                                     last_eta=last_eta,
                                                                                     transit_time=task.get('transitTime'),
                                                                                     check_transshipment=check_transshipment)
                        leg_list:list =[]
                        for index, legs in enumerate(task['leg'], start=1):
                            vessel_imo: str | None = str(legs['vessel'].get('IMO')) if legs.get('vessel') else None
                            vessel_name:str |None  = deepget(legs,'vessel','name')
                            check_service = legs.get('service')
                            leg_tt:int = legs.get('transitTime')
                            if index == 1:
                                final_etd: str = legs['fromPoint'].get('etd', first_etd)
                                final_eta: str = legs['toPoint'].get('eta',(datetime.strptime(final_etd, "%Y-%m-%dT%H:%M:%S.000Z") + timedelta(days=leg_tt)).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
                            else:
                                final_eta: str = legs['toPoint'].get('eta', last_eta)
                                final_etd: str = legs['toPoint'].get('etd', (datetime.strptime(final_eta,"%Y-%m-%dT%H:%M:%S.000Z") + timedelta(days=-(leg_tt))).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
                            leg_transit_time:int = leg_tt if leg_tt else ((datetime.fromisoformat(final_eta[:10]) - datetime.fromisoformat(final_etd[:10])).days)
                            leg_list.append(mapping_template.produce_leg_body(
                                origin_un_name=legs['fromPoint']['location']['name'],
                                origin_un_code=legs['fromPoint']['location']['unlocode'],
                                origin_term_name=legs['fromPoint']['location']['facility']['name'] if legs['fromPoint']['location'].get('facility') else None,
                                origin_term_code=legs['fromPoint']['location']['facility']['code'] if legs['fromPoint']['location'].get('facility') else None,
                                dest_un_name=legs['toPoint']['location']['name'],
                                dest_un_code=legs['toPoint']['location']['unlocode'],
                                dest_term_name=legs['toPoint']['location']['facility']['name'] if legs['toPoint']['location'].get('facility') else None,
                                dest_term_code=legs['toPoint']['location']['facility']['code'] if legs['toPoint']['location'].get('facility') else None,
                                etd=final_etd,
                                eta=final_eta,
                                tt=legs.get('transitTime',leg_transit_time),
                                cy_cutoff = legs['fromPoint'].get('defaultCutoff'),
                                transport_type=str(legs['transportMode']).title(),
                                transport_name=legs['vessel']['name'] if vessel_imo and vessel_name != '---' else None,
                                reference_type='IMO' if vessel_imo and vessel_imo not in (9999999,'None') else None,
                                reference=None if vessel_imo in (9999999,'None') else vessel_imo,
                                service_name=legs['service']['name']if check_service else None ,
                                service_code=legs['service']['code']if check_service else None,
                                internal_voy=legs.get('internalVoyageNumber'),external_voy=legs.get('externalVoyageNumber')))
                        total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body,legs=leg_list))
            return total_schedule_list
