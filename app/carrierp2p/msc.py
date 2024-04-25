import jwt
import base64
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from app.schemas import schema_response
from uuid import uuid5,NAMESPACE_DNS,UUID
from fastapi import BackgroundTasks
from base64 import b64decode
from typing import Generator,Iterator,AsyncIterator

carrier_code: str = 'MSCU'
def process_response_data(task: dict, direct_only:bool |None,vessel_imo: str, service: str, tsp: str) -> Iterator:
    check_service_code: bool = any(service_desc.get('Service') and service_desc['Service']['Description'] == service for service_desc in task['Schedules']) if service else True
    check_transshipment: bool = len(task.get('Schedules')) > 1
    transshipment_port = any(tsport['Calls'][0]['Code'] == tsp for tsport in task['Schedules'][1:]) if check_transshipment and tsp else False
    check_vessel_imo: bool = any( imo for imo in task['Schedules'] if imo.get('IMONumber') == vessel_imo) if vessel_imo else True
    if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and check_service_code and check_vessel_imo:
        first_point_from: str = task['Schedules'][0]['Calls'][0]['Code']
        last_point_to: str = task['Schedules'][-1]['Calls'][-1]['Code']
        first_etd: str = next(ed['CallDateTime'] for ed in task['Schedules'][0]['Calls'][0]['CallDates'] if ed['Type'] == 'ETD')
        last_eta: str = next(ed['CallDateTime'] for ed in task['Schedules'][-1]['Calls'][-1]['CallDates'] if ed['Type'] == 'ETA')
        transit_time:int = int((datetime.fromisoformat(last_eta) - datetime.fromisoformat(first_etd)).days)
        leg_list: list = [schema_response.Leg.model_construct(
            pointFrom={'locationName': leg['Calls'][0]['Name'], 'locationCode': leg['Calls'][0]['Code'],
                       'terminalName': leg['Calls'][0]['EHF']['Description'],
                       'terminalCode': leg['Calls'][0]['DepartureEHFSMDGCode'] if leg['Calls'][0]['DepartureEHFSMDGCode'] != '' else None},
            pointTo={'locationName': leg['Calls'][-1]['Name'], 'locationCode': leg['Calls'][-1]['Code'],
                     'terminalName': leg['Calls'][-1]['EHF']['Description'],
                     'terminalCode': leg['Calls'][-1]['ArrivalEHFSMDGCode'] if leg['Calls'][-1]['ArrivalEHFSMDGCode'] != '' else None},
            etd=(etd := next(led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if led['Type'] == 'ETD')),
            eta=(eta := next(lea['CallDateTime'] for lea in leg['Calls'][-1]['CallDates'] if lea['Type'] == 'ETA')),
            transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
            cutoffs={'docCutoffDate': si_cutoff,
                     'cyCutoffDate': next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if led.get('CallDateTime') and led['Type'] == 'CYCUTOFF'), None),
                     'vgmCutoffDate': next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if led.get('CallDateTime') and led['Type'] == 'VGM'), None)}
            if (si_cutoff := next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if led['Type'] == 'SI' and led.get('CallDateTime')), None)) else None,
            transportations={'transportType': 'Vessel', 'transportName': leg.get('TransportationMeansName'),
                             'referenceType': 'IMO' if (imo_code := leg.get('IMONumber')) and imo_code != '' else None,
                             'reference': imo_code if imo_code != '' else None},
            services={'serviceCode': leg['Service']['Description']} if leg.get('Service') else None,
            voyages={'internalVoyage': leg['Voyages'][0]['Description'] if leg.get('Voyages') else None}) for leg in task['Schedules']]
        schedule_body: dict = schema_response.Schedule.model_construct(scac=carrier_code,
                                                                       pointFrom=first_point_from,
                                                                       pointTo=last_point_to, etd=first_etd,
                                                                       eta=last_eta,
                                                                       transitTime=transit_time,
                                                                       transshipment=check_transshipment,
                                                                       legs=leg_list).model_dump(warnings=False)
        yield schedule_body


async def get_msc_token(client:HTTPXClientWrapper,background_task:BackgroundTasks, oauth: str, aud: str, rsa:str, msc_client: str, msc_scope: str, msc_thumbprint: str) ->AsyncIterator:
    msc_token_key:UUID = uuid5(NAMESPACE_DNS, 'msc-token-uuid-kuehne-nagel')
    response_token:dict = await db.get(key=msc_token_key)
    if response_token is None:
        x5t: bytes = base64.b64encode(bytearray.fromhex(msc_thumbprint))
        payload_header: dict = {'x5t': x5t.decode(), 'typ': 'JWT'}
        payload_data: dict = {'aud': aud,'iss': msc_client,'sub': msc_client,'exp': datetime.now(tz=timezone.utc) + timedelta(hours=2),'nbf': datetime.now(tz=timezone.utc)}
        private_rsa_key = serialization.load_pem_private_key(b64decode(rsa), password=None,backend=default_backend())
        encoded: str = jwt.encode(headers=payload_header, payload=payload_data, key=private_rsa_key, algorithm='RS256')
        params: dict = {'scope': msc_scope,'client_id': msc_client,'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer','grant_type': 'client_credentials', 'client_assertion': encoded}
        headers: dict = {'Content-Type': 'application/x-www-form-urlencoded'}
        response_token:dict = await anext(client.parse(background_tasks =background_task,method='POST',url=oauth, headers=headers, data=params,token_key=msc_token_key,expire = timedelta(minutes=40)))
    yield response_token['access_token']

async def get_msc_p2p(client:HTTPXClientWrapper, background_task:BackgroundTasks,url: str, oauth: str, aud: str, pw: str, msc_client: str, msc_scope: str,msc_thumbprint: str, pol: str, pod: str,
                      search_range: int, start_date_type: str,start_date: datetime.date, direct_only: bool |None, vessel_imo: str | None = None, service: str | None = None, tsp: str | None = None) -> Generator:
    params: dict = {'fromPortUNCode': pol, 'toPortUNCode': pod, 'fromDate': start_date,'toDate': (start_date + timedelta(days=search_range)).strftime("%Y-%m-%d"), 'datesRelated': start_date_type}
    token = await anext(get_msc_token(client=client,background_task=background_task,oauth=oauth, aud=aud, rsa=pw, msc_client=msc_client, msc_scope=msc_scope,msc_thumbprint=msc_thumbprint))
    headers: dict = {'Authorization': f'Bearer {token}'}
    response_json:dict = await anext(client.parse(method='GET', url=url, params=params, headers=headers))
    if response_json:
        p2p_schedule: Generator = (schedule_result for task in response_json['MSCSchedule']['Transactions'] for schedule_result in process_response_data(task=task,direct_only=direct_only, vessel_imo=vessel_imo, service=service,tsp=tsp))
        return p2p_schedule

