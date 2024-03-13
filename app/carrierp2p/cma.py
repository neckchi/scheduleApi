import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from datetime import datetime
from typing import Generator


def process_response_data(task: dict,carrier_list:dict) -> list:
    default_etd_eta = datetime.now().astimezone().replace(microsecond=0).isoformat()
    transit_time:int = task['transitTime']
    first_point_from:str = task['routingDetails'][0]['pointFrom']['location']['internalCode']
    last_point_to:str = task['routingDetails'][-1]['pointTo']['location']['internalCode']
    first_etd = next((ed['pointFrom']['departureDateLocal'] for ed in task['routingDetails'] if ed['pointFrom'].get('departureDateLocal')), default_etd_eta)
    last_eta = next((ea['pointTo']['arrivalDateLocal'] for ea in task['routingDetails'][::-1] if ea['pointTo'].get('arrivalDateLocal')), default_etd_eta)
    check_transshipment:bool = len(task['routingDetails']) > 1
    leg_list: list = [schema_response.Leg.model_construct(
        pointFrom={'locationName': leg['pointFrom']['location']['name'],
                   'locationCode': leg['pointFrom']['location']['internalCode'],
                   'terminalName': deepget(leg['pointFrom']['location'], 'facility', 'name'),
                   'terminalCode':check_pol_terminal[0].get('codification') if (check_pol_terminal := deepget(leg['pointFrom']['location'], 'facility','facilityCodifications')) else None},
        pointTo={'locationName': leg['pointTo']['location']['name'],
                 'locationCode': leg['pointTo']['location']['internalCode'],
                 'terminalName': deepget(leg['pointTo']['location'], 'facility', 'name'),
                 'terminalCode':check_pod_terminal[0].get('codification') if (check_pod_terminal := deepget(leg['pointTo']['location'], 'facility','facilityCodifications')) else None},
        etd=leg['pointFrom'].get('departureDateLocal', default_etd_eta),
        eta=leg['pointTo'].get('arrivalDateLocal', default_etd_eta),
        transitTime=leg.get('legTransitTime', 0),
        transportations={'transportType': str(leg['transportation']['meanOfTransport']).title(),
                         'transportName': deepget(leg['transportation'], 'vehicule', 'vehiculeName'),
                         'referenceType': 'IMO' if (vessel_imo := deepget(leg['transportation'], 'vehicule', 'reference')) else None,
                         'reference':vessel_imo},
        services={'serviceCode': service_name} if (service_name := deepget(leg['transportation'], 'voyage', 'service', 'code')) else None,
        voyages={'internalVoyage': voyage_num} if (voyage_num := deepget(leg['transportation'], 'voyage', 'voyageReference')) else None,
        cutoffs={'docCutoffDate':deepget(leg['pointFrom']['cutOff'], 'shippingInstructionAcceptance','local'),
                 'cyCutoffDate':deepget(leg['pointFrom']['cutOff'], 'portCutoff', 'local'),
                 'vgmCutoffDate':deepget(leg['pointFrom']['cutOff'], 'vgm', 'local')} if leg['pointFrom'].get('cutOff') else None)for leg in task['routingDetails']]
    schedule_body: dict = schema_response.Schedule.model_construct(scac=carrier_list.get(task['shippingCompany']), pointFrom=first_point_from,
                                                                   pointTo=last_point_to, etd=first_etd,eta=last_eta,
                                                                   transitTime=transit_time,transshipment=check_transshipment,
                                                                   legs=leg_list).model_dump(warnings=False)
    yield schedule_body

async def get_all_schedule(client:HTTPXClientWrapper,cma_list:list,url:str,headers:dict,params:dict,extra_condition:bool):
    updated_params = lambda cma_internal_code: dict(params,**{'shippingCompany': cma_internal_code ,'specificRoutings': 'USGovernment' if cma_internal_code == '0015' and extra_condition else 'Commercial'})
    p2p_resp_tasks: list = [asyncio.create_task(anext(client.parse(method='GET', url=url,params= updated_params(cma_internal_code=cma_code),headers=headers))) for cma_code in cma_list]
    all_schedule:list = []
    for response in asyncio.as_completed(p2p_resp_tasks):
        awaited_response = await response
        check_extension:bool = awaited_response is not None and not isinstance(awaited_response,list) and awaited_response.status_code == 206
        all_schedule.extend(awaited_response.json() if check_extension else awaited_response) if awaited_response else...
        if check_extension: # Each json response might have more than 49 results.if true, CMA will return http:206 and ask us to loop over the pages in order to get all the results from them
            page: int = 50
            last_page: int = int((awaited_response.headers['content-range']).partition('/')[2])
            cma_code_header:str = awaited_response.headers['X-Shipping-Company-Routings']
            check_if_header:bool = len(cma_code_header.split(',')) > 1  # if it contains mutiple value, we should leave 'shippingCompany' blank  so that we can return all schedules from CMA
            extra_tasks: list = [asyncio.create_task(anext(client.parse(method='GET', url=url,params=updated_params(cma_internal_code=cma_code_header) if not check_if_header else  dict(params,**{'specificRoutings':'Commercial'}),
                                                                        headers=dict(headers, **{'range': f'{num}-{49 + num}'})))) for num in range(page, last_page, page)]
            for extra_p2p in asyncio.as_completed(extra_tasks):
                result = await extra_p2p
                all_schedule.extend(result.json())
    yield all_schedule

async def get_cma_p2p(client:HTTPXClientWrapper,url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool | None,tsp: str | None = None,vessel_imo:str | None = None,
                          departure_date: datetime.date = None,arrival_date: datetime.date = None, scac: str | None = None, service: str | None = None):
    carrier_code: dict = {'0001': 'CMDU', '0002': 'ANNU','0011': 'CHNL', '0015': 'APLU'}
    api_carrier_code: str = next(k for k, v in carrier_code.items() if v == scac.upper()) if scac else None
    headers: dict = {'keyID': pw}
    params: dict = {'placeOfLoading': pol, 'placeOfDischarge': pod,'departureDate': departure_date,'arrivalDate': arrival_date, 'searchRange': search_range,
                    'maxTs': 3 if direct_only in (False,None) else 0,'polVesselIMO':vessel_imo,'polServiceCode': service, 'tsPortCode': tsp}
    extra_condition: bool = True if pol.startswith('US') and pod.startswith('US') else False
    cma_list:list = [None, '0015'] if api_carrier_code is None else [api_carrier_code]
    response_json = await anext(get_all_schedule(client=client,url=url,headers=headers,params=params,cma_list=cma_list,extra_condition=extra_condition))
    if response_json:
        p2p_schedule: Generator = (schedule_result for task in  response_json for schedule_result in process_response_data(task=task,carrier_list = carrier_code))
        return p2p_schedule




