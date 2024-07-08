import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from app.schemas import schema_response
from datetime import datetime
from typing import Generator,Iterator,AsyncIterator
from app.schemas.schema_request import CMA_GROUP



DEFAULT_ETD_ETA = datetime.now().astimezone().replace(microsecond=0).isoformat()
def extract_transportation(transportation:dict):
    """Map the transportation Details"""
    mean_of_transport:str = str(transportation['meanOfTransport']).title()
    vehicule:dict = transportation.get('vehicule', {})
    vessel_imo:str = vehicule.get('reference')
    vehicule_type:str = vehicule.get('vehiculeType')
    reference_type:str|None = None
    reference:str|None = None
    if vessel_imo and len(vessel_imo) < 9:
        reference_type:str = 'IMO'
        reference:str = vessel_imo
    elif vehicule_type == 'Barge':
        reference_type:str = 'IMO'
        reference:str = '9'
    yield {'transportType': mean_of_transport,'transportName': vehicule.get('vehiculeName'),'referenceType': reference_type,'reference': reference}
def process_response_data(task: dict,direct_only:bool |None,) -> Iterator:
    """Map the schedule and leg body"""
    transit_time:int = task['transitTime']
    first_point_from:str = task['routingDetails'][0]['pointFrom']['location'].get('internalCode') or task['routingDetails'][0]['pointFrom']['location']['locationCodifications'][0]['codification']
    last_point_to:str = task['routingDetails'][-1]['pointTo']['location'].get('internalCode') or  task['routingDetails'][-1]['pointTo']['location']['locationCodifications'][0]['codification']
    first_etd = next((ed['pointFrom']['departureDateLocal'] for ed in task['routingDetails'] if ed['pointFrom'].get('departureDateLocal')), DEFAULT_ETD_ETA)
    last_eta = next((ea['pointTo']['arrivalDateLocal'] for ea in task['routingDetails'][::-1] if ea['pointTo'].get('arrivalDateLocal')), DEFAULT_ETD_ETA)
    check_transshipment:bool = len(task['routingDetails']) > 1
    if (direct_only is None or direct_only != check_transshipment):
        leg_list: list = [schema_response.LEG_ADAPTER.dump_python({
            'pointFrom':{'locationName': leg['pointFrom']['location']['name'],
                       'locationCode': leg['pointFrom']['location'].get('internalCode') or leg['pointFrom']['location']['locationCodifications'][0]['codification'],
                       'terminalName': deepget(leg['pointFrom']['location'], 'facility', 'name'),
                       'terminalCode':check_pol_terminal[0].get('codification') if (check_pol_terminal := deepget(leg['pointFrom']['location'], 'facility','facilityCodifications')) else None},
            'pointTo':{'locationName': leg['pointTo']['location']['name'],
                     'locationCode': leg['pointTo']['location'].get('internalCode') or leg['pointTo']['location']['locationCodifications'][0]['codification'],
                     'terminalName': deepget(leg['pointTo']['location'], 'facility', 'name'),
                     'terminalCode':check_pod_terminal[0].get('codification') if (check_pod_terminal := deepget(leg['pointTo']['location'], 'facility','facilityCodifications')) else None},
            'etd':leg['pointFrom'].get('departureDateLocal', DEFAULT_ETD_ETA),
            'eta':leg['pointTo'].get('arrivalDateLocal', DEFAULT_ETD_ETA),
            'transitTime':leg.get('legTransitTime', 0),
            'transportations':next(extract_transportation(leg['transportation'])),
            'services':{'serviceCode': service_name} if (service_name := deepget(leg['transportation'], 'voyage', 'service', 'code')) else None,
            'voyages':{'internalVoyage': voyage_num if (voyage_num := deepget(leg['transportation'], 'voyage', 'voyageReference')) else None},
            'cutoffs':{'docCutoffDate':deepget(leg['pointFrom']['cutOff'], 'shippingInstructionAcceptance','local'),
                     'cyCutoffDate':deepget(leg['pointFrom']['cutOff'], 'portCutoff', 'local'),
                     'vgmCutoffDate':deepget(leg['pointFrom']['cutOff'], 'vgm', 'local')} if leg['pointFrom'].get('cutOff') else None},warnings=False) for leg in task['routingDetails']]
        schedule_body: dict = schema_response.SCHEDULE_ADAPTER.dump_python({'scac':CMA_GROUP.get(task['shippingCompany']), 'pointFrom':first_point_from,'pointTo':last_point_to, 'etd':first_etd,'eta':last_eta,
                                                                       'transitTime':transit_time,'transshipment':check_transshipment,'legs':leg_list},warnings=False)
        yield schedule_body

async def get_all_schedule(client:HTTPXClientWrapper,cma_list:list,url:str,headers:dict,params:dict,extra_condition:bool) ->AsyncIterator:
    """each json response from CMA only contains 49 scehdule. if CAM can offer more schedule, the http sts will be 206.we can then adjust the 'range' to get more schedule
    this function will extend the json response if http sts == 206 else will only return the first json response"""
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
                          departure_date: datetime.date = None,arrival_date: datetime.date = None, scac: str | None = None, service: str | None = None) -> Generator:
    api_carrier_code: str = next(k for k, v in CMA_GROUP.items() if v == scac.upper()) if scac else None
    headers: dict = {'keyID': pw}
    params: dict = {'placeOfLoading': pol, 'placeOfDischarge': pod,'departureDate': departure_date,'arrivalDate': arrival_date, 'searchRange': search_range,'polVesselIMO':vessel_imo,'polServiceCode': service, 'tsPortCode': tsp}
    extra_condition: bool = True if pol.startswith('US') and pod.startswith('US') else False
    cma_list:list = [None, '0015'] if api_carrier_code is None else [api_carrier_code]
    response_json = await anext(get_all_schedule(client=client,url=url,headers=headers,params=params,cma_list=cma_list,extra_condition=extra_condition))
    if response_json:
        p2p_schedule: Generator = (schedule_result for task in  response_json for schedule_result in process_response_data(task=task,direct_only=direct_only))
        return p2p_schedule



