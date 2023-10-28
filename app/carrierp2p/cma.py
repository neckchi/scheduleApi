import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from datetime import datetime
from app.carrierp2p import mapping_template


# Check API status
# https://cma-status-prod.checklyhq.com/

async def get_cma_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool | None,tsp: str | None = None,
                          departure_date: datetime.date = None,
                          arrival_date: datetime.date = None, scac: str | None = None, service: str | None = None):
    default_etd_eta = datetime.now().astimezone().replace(microsecond=0).isoformat()
    carrier_code: dict = {'0001': 'CMDU', '0002': 'ANNU','0011': 'CHNL', '0014': 'CSFU', '0015': 'APLU'}
    api_carrier_code: str = next(k for k, v in carrier_code.items() if v == scac.upper()) if scac else None
    headers: dict = {'keyID': pw}
    params: dict = {'placeOfLoading': pol, 'placeOfDischarge': pod,'departureDate': departure_date,'arrivalDate': arrival_date, 'searchRange': search_range, 'maxTs': 3 if direct_only in (False,None) else 0,'polServiceCode': service, 'tsPortCode': tsp}
    cma_list:set = {None, '0015'} if api_carrier_code is None else {api_carrier_code}
    extra_condition: bool = True if pol.startswith('US') and pod.startswith('US') else False

    """
    Shippingcompany 0015 (APL) is excluded and works as a separate entity. Usually, customers asking for APL route only wants APL.
    It is the reason why we search for APL schedule, commercial routes of other carriers are not suggested.
    APL is mainly used for US government looking for US military/Gov routes by using the parameter specificRoutings populated with “USGovernment”
    If commercial routes are not defined for a shipping company, you will get solutions of the other shipping companies (except for APL)
    """

    p2p_resp_tasks: list = [asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url,params=dict(params,
    **{'shippingCompany': cma_code,'specificRoutings': 'USGovernment' if cma_code == '0015' and extra_condition else 'Commercial'}),headers=headers))) for cma_code in cma_list]
    total_schedule_list:list =[]
    for response in asyncio.as_completed(p2p_resp_tasks):
        awaited_response = await response
        check_extension:bool = awaited_response is not None and  type(awaited_response) != list and awaited_response.status_code == 206
        response_json: list = awaited_response.json() if check_extension else awaited_response

        # Each json response might have more than 49 results.if true, CMA will return http:206 and ask us to loop over the pages in order to get all the results from them
        if check_extension:
            page: int = 50
            last_page: int = int((awaited_response.headers['content-range']).partition('/')[2])
            cma_code: str = awaited_response.headers['X-Shipping-Company-Routings']
            extra_tasks: set = set()
            for n in range(page, last_page, page):
                r: str = f'{n}-{49 + n}'
                extra_tasks.add((asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url,params=dict(params,
                **{'shippingCompany': cma_code,'specificRoutings': 'USGovernment' if cma_code == '0015' and extra_condition else 'Commercial'}),headers=dict(headers, **{'range': r}))))))
            for extra_p2p in asyncio.as_completed(extra_tasks):
                result = await extra_p2p
                response_json.extend(result.json())

        if response_json:
        # if awaited_response.status_code in (200, 206):
            for task in response_json:
                transit_time:int = task['transitTime']
                first_point_from:str = task['routingDetails'][0]['pointFrom']['location']['internalCode']
                last_point_to:str = task['routingDetails'][-1]['pointTo']['location']['internalCode']
                first_etd = next((ed['pointFrom']['departureDateLocal'] for ed in task['routingDetails'] if ed['pointFrom'].get('departureDateLocal')), default_etd_eta)
                last_eta = next((ea['pointTo']['arrivalDateLocal'] for ea in task['routingDetails'][::-1] if ea['pointTo'].get('arrivalDateLocal')), default_etd_eta)
                first_cy_cutoff = next((cyc['pointFrom']['portCutoffDate'] for cyc in task['routingDetails'] if deepget(cyc['pointFrom'],'portCutoffDate')), None)
                first_vgm_cuttoff = next((vgmc['pointFrom']['vgmCutoffDate'] for vgmc in task['routingDetails'] if deepget(vgmc['pointFrom'],'vgmCutoffDate')), None)
                first_doc_cutoff = next((doc['pointFrom']['cutOff']['shippingInstructionAcceptance']['local'] for doc in task['routingDetails'] if deepget(doc['pointFrom'],'cutOff', 'shippingInstructionAcceptance', 'local')), None)
                check_transshipment:bool = len(task['routingDetails']) > 1
                schedule_body: dict = mapping_template.produce_schedule_body(
                    carrier_code=carrier_code.get(task['shippingCompany']),
                    first_point_from=first_point_from,
                    last_point_to=last_point_to,
                    first_etd=first_etd,
                    last_eta=last_eta, cy_cutoff=first_cy_cutoff, doc_cutoff=first_doc_cutoff,
                    vgm_cutoff=first_vgm_cuttoff,
                    transit_time=transit_time,
                    check_transshipment=check_transshipment)

                leg_list:list=[]
                for legs in task['routingDetails']:
                    check_pol_terminal:dict|None =deepget(legs['pointFrom']['location'],'facility','facilityCodifications')
                    check_pod_terminal:dict|None = deepget(legs['pointTo']['location'],'facility','facilityCodifications')
                    check_cut_offs = legs['pointFrom'].get('cutOff')
                    vessel_imo = deepget(legs['transportation'],'vehicule','reference')
                    leg_list.append(mapping_template.produce_leg_body(
                        origin_un_name=legs['pointFrom']['location']['name'],
                        origin_un_code=legs['pointFrom']['location']['internalCode'],
                        origin_term_name=deepget(legs['pointFrom']['location'],'facility', 'name'),
                        origin_term_code=check_pol_terminal[0].get('codification') if check_pol_terminal else None,
                        dest_un_name=legs['pointTo']['location']['name'],
                        dest_un_code=legs['pointTo']['location']['internalCode'],
                        dest_term_name=deepget(legs['pointTo']['location'],'facility','name'),
                        dest_term_code=check_pod_terminal[0].get('codification') if check_pod_terminal else None,
                        etd=legs['pointFrom'].get('departureDateLocal',default_etd_eta),
                        eta=legs['pointTo'].get('arrivalDateLocal',default_etd_eta),
                        tt=legs.get('legTransitTime',0),
                        cy_cutoff=deepget(legs['pointFrom']['cutOff'], 'portCutoff', 'local') if check_cut_offs else None,
                        si_cutoff=deepget(legs['pointFrom']['cutOff'], 'shippingInstructionAcceptance','local')if check_cut_offs else None,
                        vgm_cutoff=deepget(legs['pointFrom']['cutOff'], 'vgm', 'local')if check_cut_offs else None,
                        transport_type=str(legs['transportation']['meanOfTransport']).title(),
                        transport_name=deepget(legs['transportation'],'vehicule','vehiculeName'),
                        reference_type='IMO' if vessel_imo else None,
                        reference=vessel_imo,
                        service_code=deepget(legs['transportation'], 'voyage', 'service', 'code') if legs['transportation'].get('voyage') and legs['transportation']['voyage'].get('service') else None,
                        internal_voy=deepget(legs['transportation'], 'voyage', 'voyageReference')))
                total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body, legs=leg_list))
    return total_schedule_list



