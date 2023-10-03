import asyncio
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPXClientWrapper
from datetime import datetime


# Check API status
# https://cma-status-prod.checklyhq.com/

async def get_cma_p2p(client, url: str, pw: str, pol: str, pod: str, search_range: int, direct_only: bool | None,tsp: str | None = None,
                          departure_date: str | None = None,
                          arrival_date: str | None = None, scac: str | None = None, service: str | None = None):
    default_etd_eta = datetime.now().astimezone().replace(microsecond=0).isoformat()
    carrier_code: dict = {'0001': 'CMDU', '0002': 'ANNU','0011': 'CHNL', '0014': 'CSFU', '0015': 'APLU'}
    api_carrier_code: str = next(k for k, v in carrier_code.items() if v == scac.upper()) if scac else None
    headers: dict = {'keyID': pw}
    params: dict = {'placeOfLoading': pol, 'placeOfDischarge': pod,'departureDate': departure_date,'arrivalDate': arrival_date, 'searchRange': search_range, 'maxTs': 3 if direct_only in (False,None) else 0,'polServiceCode': service, 'tsPortCode': tsp}
    cma_list:set = {None, '0015'} if api_carrier_code is None else {api_carrier_code}
    extra_condition: bool = True if pol.startswith('US') and pod.startswith('US') else False
    # Performance Enhancement - No meomory is used: async generator object - schedules
    async def schedules():
        """
        Shippingcompany 0015 (APL) is excluded and works as a separate entity. Usually, customers asking for APL route only wants APL.
        It is the reason why we search for APL schedule, commercial routes of other carriers are not suggested.
        APL is mainly used for US government looking for US military/Gov routes by using the parameter specificRoutings populated with “USGovernment”
        If commercial routes are not defined for a shipping company, you will get solutions of the other shipping companies (except for APL)
        """

        p2p_resp_tasks: list = [asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url,
                                                                      params=dict(params, **{'shippingCompany': cma_code,'specificRoutings': 'USGovernment' if cma_code == '0015' and extra_condition else 'Commercial'}),
                                                                      headers=headers))) for cma_code in cma_list]

        for response in asyncio.as_completed(p2p_resp_tasks):
            response = await response
            # response_json:list = orjson.loads(response.text)
            response_json: list = response.json()
            # Each json response might have more than 49 results.if true, CMA will return http:206 and ask us to loop over the pages in order to get all the results from them
            if response.status_code == 206:
                page: int = 50
                last_page: int = int((response.headers['content-range']).partition('/')[2])
                cma_code: str = response.headers['X-Shipping-Company-Routings']
                extra_tasks: set = set()
                for n in range(page, last_page, page):
                    r: str = f'{n}-{49 + n}'
                    extra_tasks.add((asyncio.create_task(anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url,
                                                                           params=dict(params, **{
                                                                               'shippingCompany': cma_code,
                                                                               'specificRoutings': 'USGovernment' if cma_code == '0015' and extra_condition else 'Commercial'}),
                                                                           headers=dict(headers, **{'range': r}))))))
                for extra_p2p in asyncio.as_completed(extra_tasks):
                    result = await extra_p2p
                    response_json.extend(result.json())

            if response.status_code in (200, 206):
                for task in response_json:
                    transit_time:int = task['transitTime']
                    first_point_from:str = task['routingDetails'][0]['pointFrom']['location']['internalCode']
                    last_point_to:str = task['routingDetails'][-1]['pointTo']['location']['internalCode']
                    first_etd = next((ed['pointFrom']['departureDateLocal'] for ed in task['routingDetails'] if ed['pointFrom'].get('departureDateLocal')), default_etd_eta)
                    last_eta = next((ea['pointTo']['arrivalDateLocal'] for ea in task['routingDetails'][::-1] if ea['pointTo'].get('arrivalDateLocal')), default_etd_eta)
                    first_cy_cutoff = next((cyc['pointFrom']['portCutoffDate'] for cyc in task['routingDetails'] if deepget(cyc['pointFrom'],'portCutoffDate')), None)
                    first_vgm_cuttoff = next((vgmc['pointFrom']['vgmCutoffDate'] for vgmc in task['routingDetails'] if deepget(vgmc['pointFrom'],'vgmCutoffDate')), None)
                    first_doc_cutoff = next((doc['pointFrom']['cutOff']['shippingInstructionAcceptance']['local'] for doc in task['routingDetails'] if deepget(doc['pointFrom'],'cutOff', 'shippingInstructionAcceptance', 'local')), None)
                    check_transshipment = True if len(task['routingDetails']) > 1 else False
                    schedule_body: dict = {'scac': carrier_code.get(task['shippingCompany']),
                                           'pointFrom': first_point_from,
                                           'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                           'cyCutOffDate': first_cy_cutoff,
                                           'docCutOffDate': first_doc_cutoff,
                                           'vgmCutOffDate': first_vgm_cuttoff,
                                           'transitTime': transit_time,
                                           'transshipment': check_transshipment}

                    # Performance Enhancement - No meomory is used:async generator object - schedule leg
                    async def schedule_leg():
                        for legs in task['routingDetails']:
                            check_pol_terminal:dict|None =deepget(legs['pointFrom']['location'],'facility','facilityCodifications')
                            check_pod_terminal:dict|None = deepget(legs['pointTo']['location'],'facility','facilityCodifications')
                            vessel_imo = deepget(legs['transportation'],'vehicule','reference')
                            leg_body: dict = {'pointFrom': {'locationName': legs['pointFrom']['location']['name'],
                                                            'locationCode': legs['pointFrom']['location']['internalCode'],
                                                            'terminalName': deepget(legs['pointFrom']['location'],'facility', 'name'),
                                                            'terminalCode': check_pol_terminal[0].get('codification') if check_pol_terminal else None
                                                            },

                                              'pointTo': {'locationName': legs['pointTo']['location']['name'],
                                                          'locationCode': legs['pointTo']['location']['internalCode'],
                                                          'terminalName': deepget(legs['pointTo']['location'],'facility','name'),
                                                          'terminalCode': check_pod_terminal[0].get('codification') if check_pod_terminal else None
                                                          },
                                              'etd': legs['pointFrom'].get('departureDateLocal',default_etd_eta) ,
                                              'eta': legs['pointTo'].get('arrivalDateLocal',default_etd_eta) ,

                                              'transitTime':legs.get('legTransitTime',0) ,

                                              'transportations': {
                                                  'transportType': str(legs['transportation']['meanOfTransport']).title(),
                                                  'transportName': deepget(legs['transportation'],'vehicule','vehiculeName'),
                                                  'referenceType': 'IMO' if vessel_imo else None,
                                                  'reference': vessel_imo
                                                                }
                                              }
                            voyage_number:str|None = deepget(legs['transportation'], 'voyage', 'voyageReference')
                            if voyage_number:
                                voyage_body:dict = {'internalVoyage': voyage_number}
                                leg_body.update({'voyages': voyage_body})

                            if legs['transportation'].get('voyage') and legs['transportation']['voyage'].get('service'):
                                service_body:dict = {'serviceCode': deepget(legs['transportation'], 'voyage', 'service', 'code')}
                                leg_body.update({'services': service_body})

                            if legs['pointFrom'].get('cutOff'):
                                cut_off_body: dict = {
                                    'bookingCutoff': deepget(legs['pointFrom']['cutOff'], 'standardBookingAcceptance','local'),
                                    'cyCuttoff': deepget(legs['pointFrom']['cutOff'], 'portCutoff', 'local'),
                                    'siCuttoff': deepget(legs['pointFrom']['cutOff'], 'shippingInstructionAcceptance','local'),
                                    'vgmCutoff': deepget(legs['pointFrom']['cutOff'], 'vgm', 'local'),
                                    'customsCutoff': deepget(legs['pointFrom']['cutOff'], 'customsAcceptance','local'),
                                    'securityFilingCutoff': deepget(legs['pointFrom']['cutOff'], 'vgm', 'local')}

                                leg_body.update({'cutoffs': cut_off_body})

                            yield leg_body

                    schedule_body.update({'legs': [sl async for sl in schedule_leg()]})

                    yield schedule_body
            else:
                pass

    yield [s async for s in schedules()]
