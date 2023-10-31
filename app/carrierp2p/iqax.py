import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from datetime import datetime,timedelta


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
                            leg_list.append(schema_response.Leg.model_construct(
                                pointFrom={'locationName': legs['fromPoint']['location']['name'],
                                           'locationCode': legs['fromPoint']['location']['unlocode'],
                                           'terminalName': legs['fromPoint']['location']['facility']['name'] if (check_origin_terminal:=legs['fromPoint']['location'].get('facility')) else None,
                                           'terminalCode':legs['fromPoint']['location']['facility']['code'] if check_origin_terminal else None},
                                pointTo={'locationName': legs['toPoint']['location']['name'],
                                         'locationCode': legs['toPoint']['location']['unlocode'],
                                         'terminalName': legs['toPoint']['location']['facility']['name'] if (check_des_terminal:=legs['toPoint']['location'].get('facility')) else None,
                                         'terminalCode':legs['toPoint']['location']['facility']['code'] if check_des_terminal else None},
                                etd=final_etd,
                                eta=final_eta,
                                transitTime=legs.get('transitTime',leg_transit_time),
                                transportations={'transportType': str(legs['transportMode']).title(),
                                                 'transportName': legs['vessel']['name'] if vessel_imo and vessel_name != '---' else None,
                                                 'referenceType': 'IMO' if vessel_imo and vessel_imo not in (9999999,'None') else None,
                                                 'reference': None if vessel_imo in (9999999,'None') else vessel_imo},
                                services={'serviceCode': legs['service']['code'],'serviceName':legs['service']['name']} if check_service else None,
                                voyages={'internalVoyage': internal_voy,'externalVoyage':legs.get('externalVoyageNumber')} if (internal_voy:=legs.get('internalVoyageNumber')) else None,
                                cutoffs={'cyCutoffDate':cy_cutoff} if (cy_cutoff:=legs['fromPoint'].get('defaultCutoff')) else None))
                        schedule_body: dict = schema_response.Schedule.model_construct(scac=task.get('carrierScac'),pointFrom=task['por']['location']['unlocode'],
                                                                                       pointTo=task['fnd']['location']['unlocode'],
                                                                                       etd=first_etd, eta=last_eta,transitTime=task.get('transitTime'),
                                                                                       transshipment=check_transshipment,legs=leg_list).model_dump(warnings=False)
                        total_schedule_list.append(schedule_body)
    return total_schedule_list
