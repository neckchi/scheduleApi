from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS
import datetime


async def get_zim_access_token(client,background_task, url: str, api_key: str, client_id: str, secret: str):
    zim_token_key = uuid5(NAMESPACE_DNS, 'zim-token-uuid-kuehne-nagel2')
    response_token = await db.get(key=zim_token_key)
    if response_token is None:
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
        transport_type:dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel'}
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
                find_cutoff = lambda cutoff_type:next((leg.get(cutoff_type) for leg in task['routeLegs'] if leg.get(cutoff_type)), None)
                first_cy_cutoff:str = find_cutoff('containerClosingDate')
                first_doc_cutoff: str = find_cutoff('docClosingDate')
                first_vgm_cutoff: str = find_cutoff('vgmClosingDate')
                schedule_body:dict = schema_response.Schedule.model_construct(scac=carrier_code,pointFrom=first_point_from,pointTo=last_point_to,etd=first_etd,eta=last_eta,
                                                                              cyCutOffDate=first_cy_cutoff,docCutOffDate=first_doc_cutoff,vgmCutOffDate=first_vgm_cutoff,
                                                                              transitTime=transit_time,transshipment=check_transshipment,
                legs=[schema_response.Leg.model_construct(
                pointFrom=  {'locationName': leg['departurePortName'],'locationCode': leg['departurePort']},
                pointTo={'locationName': leg['arrivalPortName'],'locationCode': leg['arrivalPort']},
                etd= (etd:=leg['departureDate']),
                eta=(eta:=leg['arrivalDate']),
                transitTime=int((datetime.datetime.fromisoformat(eta) - datetime.datetime.fromisoformat(etd)).days),
                transportations ={'transportType':transport_type.get(leg['vesselName'], 'Vessel'),'transportName': None if (vessel_name:=leg['vesselName']) == 'TO BE NAMED' else vessel_name,
                'referenceType': 'IMO' if (vessel_code:=leg.get('lloydsCode')) and vessel_name != 'TO BE NAMED' else None,'reference': vessel_code if vessel_name != 'TO BE NAMED' else None},
                services={'serviceCode': leg['line'] }if (voyage_num:=leg.get('voyage')) else None,
                cutoffs={'cyCutoffDate': cyoff, 'docCutoffDate':leg.get('docClosingDate'),'vgmCutoffDate': leg.get('vgmClosingDate')} if (cyoff:=leg.get('containerClosingDate')) or leg.get('docClosingDate')
                                                                                                              or  leg.get('vgmClosingDate') else None,
                voyages={'internalVoyage':voyage_num + leg['leg'],'externalVoyage':leg.get('consortSailingNumber')}if voyage_num else None) for leg in task['routeLegs']]).model_dump(warnings=False)
                total_schedule_list.append(schedule_body)
        return total_schedule_list


