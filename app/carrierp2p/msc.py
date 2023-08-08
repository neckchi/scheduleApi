import jwt
import base64
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from app.carrierp2p.helpers import call_client


async def get_msc_token(client, oauth: str, aud: str, rsa: str, msc_client: str, msc_scope: str, msc_thumbprint: str):
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
    response = await anext(call_client(client=client,method='POST',url=oauth, headers=headers, data=params))
    response_token = response.json()
    yield response_token['access_token']


async def get_msc_p2p(client, url: str, oauth: str, aud: str, pw: str, msc_client: str, msc_scope: str,
                      msc_thumbprint: str, pol: str, pod: str,
                      search_range: int, start_date_type: str,
                      start_date: str, direct_only: bool |None, service: str | None = None, tsp: str | None = None):
    params: dict = {'fromPortUNCode': pol, 'toPortUNCode': pod, 'fromDate': start_date,
                    'toDate': (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=search_range)).strftime(
                        "%Y-%m-%d"), 'datesRelated': start_date_type}

    token = await anext( get_msc_token(client=client, oauth=oauth, aud=aud, rsa=pw, msc_client=msc_client, msc_scope=msc_scope,msc_thumbprint=msc_thumbprint))
    headers: dict = {'Authorization': f'Bearer {token}'}
    response = await anext(
        call_client(client=client, method='GET', url=url, params=params, headers=headers))

    ## Performance Enhancement - No meomory is used:async generator object - schedules
    async def schedules():
        if response.status_code == 200:
            response_json:dict = response.json()
            for task in response_json['MSCSchedule']['Transactions']:
                # Additional check on service code/name in order to fullfill business requirment(query the result by service code)
                check_service_code: bool = next((True for services in task['Schedules'] if services.get('Service') and services['Service']['Description'] == service), False) if service else True
                check_transshipment: bool = True if len(task['Schedules']) > 1 else False
                transshipment_port: bool = next((True for tsport in task['Schedules'][1:] if tsport['Calls'][0]['Code'] == tsp),False) if check_transshipment and tsp else False
                if transshipment_port or not tsp:
                    if direct_only is None or (not check_transshipment  and direct_only is True) or (check_transshipment and direct_only is False) :
                        if check_service_code:
                            carrier_code:str = 'MSCU'
                            first_point_from = task['Schedules'][0]['Calls'][0]['Code']
                            last_point_to = task['Schedules'][-1]['Calls'][-1]['Code']
                            first_etd = next(ed['CallDateTime'] for ed in task['Schedules'][0]['Calls'][0]['CallDates'] if ed['Type'] == 'ETD')
                            last_eta = next(ed['CallDateTime'] for ed in task['Schedules'][-1]['Calls'][-1]['CallDates'] if ed['Type'] == 'ETA')
                            first_cy_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'CYCUTOFF' and led.get('CallDateTime')), None)
                            first_doc_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'SI' and led.get('CallDateTime')), None)
                            first_vgm_cutoff = next((led['CallDateTime'] for led in task['Schedules'][0]['Calls'][0]['CallDates'] if led['Type'] == 'VGM' and led.get('CallDateTime')), None)
                            transit_time = int((datetime.fromisoformat(last_eta) - datetime.fromisoformat(first_etd)).days)
                            schedule_body: dict = {'scac': carrier_code, 'pointFrom': first_point_from,
                                                   'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                                   'cyCutOffDate': first_cy_cutoff,
                                                   'docCutOffDate': first_doc_cutoff,
                                                   'vgmCutOffDate': first_vgm_cutoff,
                                                   'transitTime': transit_time,
                                                   'transshipment': check_transshipment
                                                   }

                            ## Performance Enhancement - No meomory is used:async generator object - schedule leg
                            async def schedule_leg():
                                for legs in task['Schedules']:
                                    etd = next(led['CallDateTime'] for led in legs['Calls'][0]['CallDates'] if led['Type'] == 'ETD')
                                    eta = next(lea['CallDateTime'] for lea in legs['Calls'][-1]['CallDates'] if lea['Type'] == 'ETA')
                                    cy = next((led['CallDateTime'] for led in legs['Calls'][0]['CallDates'] if led['Type'] == 'CYCUTOFF' and led.get('CallDateTime')), None)
                                    si = next((led['CallDateTime'] for led in legs['Calls'][0]['CallDates'] if led['Type'] == 'SI' and led.get('CallDateTime')), None)
                                    vgm = next((led['CallDateTime'] for led in legs['Calls'][0]['CallDates'] if led['Type'] == 'VGM' and led.get('CallDateTime')), None)
                                    vessel_imo = legs.get('IMONumber')
                                    leg_body: dict = {'pointFrom': {'locationCode': legs['Calls'][0]['Code'],
                                                                    'locationName': legs['Calls'][0]['Name'],
                                                                    'terminalName': legs['Calls'][0]['EHF'][
                                                                        'Description'],
                                                                    'terminalCode': legs['Calls'][0][
                                                                        'DepartureEHFSMDGCode'] if legs['Calls'][0]['DepartureEHFSMDGCode'] != '' else None
                                                                    },
                                                      'pointTo': {'locationCode': legs['Calls'][-1]['Code'],
                                                                  'locationName': legs['Calls'][-1]['Name'],
                                                                  'terminalName': legs['Calls'][-1]['EHF']['Description'],
                                                                  'terminalCode': legs['Calls'][-1]['ArrivalEHFSMDGCode'] if legs['Calls'][-1]['ArrivalEHFSMDGCode'] != '' else None
                                                                  },
                                                      'etd': etd,
                                                      'eta': eta,
                                                      'transitTime': int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
                                                      'transportations': {'transportType': 'Vessel',
                                                                          'transportName': legs['TransportationMeansName'],
                                                                          'referenceType': 'IMO' if vessel_imo and vessel_imo != '' else None,
                                                                          'reference': vessel_imo if vessel_imo != '' else None}}

                                    if legs['Voyages']:
                                        voyage_body:dict = {'internalVoyage': legs['Voyages'][0]['Description']}
                                        leg_body.update({'voyages': voyage_body})

                                    if cy and si and vgm:
                                        cut_off_body: dict = {
                                            'cyCuttoff': cy,
                                            'siCuttoff': si,
                                            'vgmCutoff': vgm}
                                        leg_body.update({'cutoffs': cut_off_body})

                                    if legs.get('Service'):
                                        service_body:dict = {'serviceName': legs['Service']['Description']}
                                        leg_body.update({'services': service_body})

                                    yield leg_body

                            schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
                            yield schedule_body
                        else:
                            pass
                    else:
                        pass
                else:
                    pass

    yield [s async for s in schedules()]

