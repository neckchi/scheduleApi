from app.routers.router_config import HTTPXClientWrapper
from datetime import datetime,timedelta
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
import logging

async def get_hlag_access_token(client,background_task, url: str,pw:str,user:str, client_id: str,client_secret:str):
    hlcu_token_key = uuid5(NAMESPACE_DNS, 'hlcu-token-uuid-kuehne-nagel')
    response_token = await db.get(key=hlcu_token_key)
    if not response_token:
        headers: dict = {'X-IBM-Client-Id': client_id,
                         'X-IBM-Client-Secret': client_secret,
                         'Accept': 'application/json'}
        body:dict = {
        'mode': "raw",
        'userId': user,
        'password': pw,
        'orgUnit': "HLAG"}

        response = await anext(HTTPXClientWrapper.call_client(method='POST',background_tasks =background_task,client=client,url=url, headers=headers,json=body,token_key=hlcu_token_key,expire=timedelta(minutes=10)))
        response_token = response.json()
    yield response_token['token']

async def get_hlag_p2p(client,background_task, url: str, turl: str,user:str, pw: str, client_id: str,client_secret:str,pol: str, pod: str,search_range: int,
                       etd: str | None, eta: str | None, direct_only: bool|None = None,vessel_flag:str|None = None,service: str | None = None, tsp: str | None = None):
    logging.info(f'url: {url} \n turl {turl} \n user {user} \n pw {pw} \n client_id {client_id} \n client_secret {client_secret}')
    start_day:str = datetime.strptime(etd, "%Y-%m-%d").strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else datetime.strptime(eta, "%Y-%m-%d").strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    end_day:str = (datetime.strptime(etd, "%Y-%m-%d") + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ") if etd else (datetime.strptime(eta, "%Y-%m-%d") + timedelta(days=search_range)).strftime("%Y-%m-%dT%H:%M:%S.%SZ")
    params: dict = {'placeOfReceipt': pol, 'placeOfDelivery': pod}
    params.update({'earliestDepartureDateTime': start_day,'latestDepartureDateTime':end_day}) if etd else params.update({'earliestArrivalDateTime': start_day,'arrivalEndDateTime':end_day})
    params.update({'routingTypeCode': direct_only}) if direct_only is not None else...
    params.update({'vesselFlag': vessel_flag}) if vessel_flag is not None else ...
    token = await anext(get_hlag_access_token(client=client,background_task=background_task, url=turl,user=user, pw=pw, client_id= client_id,client_secret = client_secret))
    headers: dict = {'X-IBM-Client-Id': client_id,'X-IBM-Client-Secret': client_secret, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    response = await anext(HTTPXClientWrapper.call_client(client=client, method='GET', url=url, params=params,headers=headers))
    async def schedules():
        if response.status_code == 200:
            response_json: dict = response.json()
            for task in response_json:
                first_point_from:str = task['placeOfReceipt']
                last_point_to:str = task['placeOfDelivery']
                first_etd:datetime = task['placeOfReceiptDateTime']
                last_eta:datetime = task['placeOfDeliveryDateTime']
                transit_time: int = task.get('transitTime',(datetime.fromisoformat(last_eta[:10]) - datetime.fromisoformat(first_etd[:10])).days)
                first_cy_cutoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'FCO'), None)
                first_vgm_cuttoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'VCO'), None)
                first_doc_cutoff:datetime  = next((cutoff['cutOffDateTime'] for cutoff in task['gateInCutOffDateTimes'] if cutoff['cutOffDateTimeCode'] == 'LCO'), None)
                check_transshipment:bool = True if len(task['legs']) > 1 else False
                schedule_body: dict = {'scac': 'HLCU',
                                       'pointFrom': first_point_from,
                                       'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                       'cyCutOffDate': first_cy_cutoff,
                                       'docCutOffDate': first_doc_cutoff,
                                       'vgmCutOffDate': first_vgm_cuttoff,
                                       'transitTime': transit_time,
                                       'transshipment': check_transshipment}

                async def schedule_leg():
                    for legs in task['legs']:
                        vessel_imo:str = legs.get('vesselImoNumber')
                        etd:str = legs['departureDateTime']
                        eta:str = legs['arrivalDateTime']
                        leg_body: dict = {'pointFrom': {'locationName': legs['departureLocation']['locationName'],
                                                        'locationCode': legs['departureLocation']['UNLocationCode']},

                                          'pointTo': {'locationName': legs['arrivalLocation']['locationName'],
                                                      'locationCode': legs['arrivalLocation']['UNLocationCode']},
                                          'etd': etd,
                                          'eta': eta,
                                          'transitTime': int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                                          'transportations': {
                                              'transportType': str(legs['modeOfTransport']).title(),
                                              'transportName': legs['vesselName'] if vessel_imo else None,
                                              'referenceType': 'IMO' if vessel_imo and vessel_imo != '0000000' else None ,
                                              'reference': vessel_imo if vessel_imo != '0000000' else None
                                          }
                                          }
                        voyage_number: str | None = legs.get('importVoyageNumber')
                        if voyage_number:
                            voyage_body: dict = {'internalVoyage': voyage_number}
                            leg_body.update({'voyages': voyage_body})

                        service_name:str|None = legs.get('serviceName')
                        if service_name:
                            service_body: dict = {'serviceCode':None,'serviceName':service_name}
                            leg_body.update({'services': service_body})

                        yield leg_body

                schedule_body.update({'legs': [sl async for sl in schedule_leg()]})

                yield schedule_body
            else:pass

    yield [s async for s in schedules()]