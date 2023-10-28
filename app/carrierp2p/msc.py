import jwt
import base64
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from app.routers.router_config import HTTPXClientWrapper
from app.background_tasks import db
from uuid import uuid5,NAMESPACE_DNS
from app.carrierp2p import mapping_template


async def get_msc_token(client,background_task, oauth: str, aud: str, rsa: str, msc_client: str, msc_scope: str, msc_thumbprint: str):
    msc_token_key = uuid5(NAMESPACE_DNS, 'msc-token-uuid-kuehne-nagel')
    response_token = await db.get(key=msc_token_key)
    if not response_token:
        x5t: bytes = base64.b64encode(bytearray.fromhex(msc_thumbprint))
        payload_header: dict = {'x5t': x5t.decode(), 'typ': 'JWT'}
        payload_data: dict = {'aud': aud,
                              'iss': msc_client,
                              'sub': msc_client,
                              'exp': datetime.now(tz=timezone.utc) + timedelta(hours=2),
                              'nbf': datetime.now(tz=timezone.utc)}
        private_rsakey = serialization.load_pem_private_key(rsa.encode('utf8'), password=None,backend=default_backend())
        encoded: str = jwt.encode(headers=payload_header, payload=payload_data, key=private_rsakey, algorithm='RS256')
        params: dict = {'scope': msc_scope,
                        'client_id': msc_client,
                        'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                        'grant_type': 'client_credentials', 'client_assertion': encoded}
        headers: dict = {'Content-Type': 'application/x-www-form-urlencoded'}
        response_token = await anext(HTTPXClientWrapper.call_client(client=client,background_tasks =background_task,method='POST',url=oauth, headers=headers, data=params,token_key=msc_token_key,expire = timedelta(minutes=40)))
    yield response_token['access_token']



async def get_msc_p2p(client, background_task,url: str, oauth: str, aud: str, pw: str, msc_client: str, msc_scope: str,
                      msc_thumbprint: str, pol: str, pod: str,
                      search_range: int, start_date_type: str,
                      start_date: datetime.date, direct_only: bool |None, service: str | None = None, tsp: str | None = None):
    params: dict = {'fromPortUNCode': pol, 'toPortUNCode': pod, 'fromDate': start_date,
                    'toDate': (start_date + timedelta(days=search_range)).strftime("%Y-%m-%d"), 'datesRelated': start_date_type}
    token = await anext(get_msc_token(client=client,background_task=background_task,oauth=oauth, aud=aud, rsa=pw, msc_client=msc_client, msc_scope=msc_scope,msc_thumbprint=msc_thumbprint))
    headers: dict = {'Authorization': f'Bearer {token}'}
    response_json = await anext(HTTPXClientWrapper.call_client(client=client,method='GET', url=url, params=params, headers=headers))
    if response_json:
        total_schedule_list: list = []
        for task in response_json['MSCSchedule']['Transactions']:
            check_service_code:bool = any(service_desc.get('Service') and service_desc['Service']['Description'] == service for service_desc in task['Schedules']) if service else True
            check_transshipment: bool = len(task.get('Schedules')) > 1
            transshipment_port = any(tsport['Calls'][0]['Code'] == tsp for tsport in task['Schedules'][1:]) if check_transshipment and tsp else False
            if (transshipment_port or not tsp) and (direct_only is None or check_transshipment != direct_only) and check_service_code:
                carrier_code:str = 'MSCU'
                first_point_from:str = task['Schedules'][0]['Calls'][0]['Code']
                last_point_to:str = task['Schedules'][-1]['Calls'][-1]['Code']
                first_etd = next(ed['CallDateTime'] for ed in task['Schedules'][0]['Calls'][0]['CallDates'] if ed['Type'] == 'ETD')
                last_eta = next(ed['CallDateTime'] for ed in task['Schedules'][-1]['Calls'][-1]['CallDates'] if ed['Type'] == 'ETA')
                first_cy_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'CYCUTOFF' and led.get('CallDateTime')), None)
                first_doc_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'SI' and led.get('CallDateTime')), None)
                first_vgm_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'VGM' and led.get('CallDateTime')), None)
                transit_time = int((datetime.fromisoformat(last_eta) - datetime.fromisoformat(first_etd)).days)
                schedule_body:dict = mapping_template.produce_schedule_body(
                                                                        carrier_code=carrier_code,
                                                                         first_point_from=first_point_from,
                                                                         last_point_to=last_point_to,
                                                                         first_etd=first_etd,
                                                                         last_eta=last_eta,cy_cutoff=first_cy_cutoff,doc_cutoff=first_doc_cutoff,vgm_cutoff=first_vgm_cutoff,
                                                                         transit_time=transit_time,
                                                                         check_transshipment=check_transshipment)

                leg_list:list = [mapping_template.produce_leg_body(
                        origin_un_name=leg['Calls'][0]['Name'],
                        origin_un_code=leg['Calls'][0]['Code'],
                        origin_term_name=leg['Calls'][0]['EHF']['Description'],
                        origin_term_code=leg['Calls'][0]['DepartureEHFSMDGCode'] if leg['Calls'][0]['DepartureEHFSMDGCode'] != '' else None,
                        dest_un_name=leg['Calls'][-1]['Name'],
                        dest_un_code=leg['Calls'][-1]['Code'],
                        dest_term_name=leg['Calls'][-1]['EHF']['Description'],
                        dest_term_code=leg['Calls'][-1]['ArrivalEHFSMDGCode'] if leg['Calls'][-1]['ArrivalEHFSMDGCode'] != '' else None,
                        etd=(etd:=next(led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if (cut_off_type:=led['Type']) == 'ETD')),
                        eta=(eta:=next(lea['CallDateTime'] for lea in leg['Calls'][-1]['CallDates'] if lea['Type']== 'ETA')),
                        tt=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                        cy_cutoff=next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if cut_off_type == 'CYCUTOFF' and (cut_offs:= led.get('CallDateTime'))), None),
                        si_cutoff=next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if cut_off_type == 'SI' and cut_offs), None),
                        vgm_cutoff=next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if cut_off_type == 'VGM' and cut_offs), None),
                        transport_type='Vessel',
                        transport_name=leg.get('TransportationMeansName'),
                        reference_type='IMO' if (vessel_imo := leg.get('IMONumber')) and vessel_imo != '' else None,
                        reference=vessel_imo if vessel_imo != '' else None,
                        service_code=leg['Service']['Description'] if leg.get('Service') else None,
                        internal_voy=leg['Voyages'][0]['Description'] if leg.get('Voyages') else None) for leg in task['Schedules']]
                total_schedule_list.append(mapping_template.produce_schedule(schedule=schedule_body,legs=leg_list))
        return total_schedule_list
