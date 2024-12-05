import jwt
from datetime import datetime, timedelta, timezone
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from app.internal.http.http_client_manager import HTTPClientWrapper
from app.api.schemas.schema_response import Schedule, Leg, PointBase, Cutoff, Voyage, Service, Transportation
from fastapi import BackgroundTasks
from base64 import b64decode, b64encode
from typing import Generator, Iterator, AsyncIterator


def process_leg_data(leg_task: list) -> list:
    leg_list: list = [Leg.model_construct(
        pointFrom=PointBase.model_construct(locationName=leg['Calls'][0]['Name'], locationCode=leg['Calls'][0]['Code'],
                                            terminalName=leg['Calls'][0]['EHF']['Description'],
                                            terminalCode=leg['Calls'][0]['DepartureEHFSMDGCode'] if leg['Calls'][0][
                                                                                                        'DepartureEHFSMDGCode'] != '' else None),
        pointTo=PointBase.model_construct(locationName=leg['Calls'][-1]['Name'], locationCode=leg['Calls'][-1]['Code'],
                                          terminalName=leg['Calls'][-1]['EHF']['Description'],
                                          terminalCode=leg['Calls'][-1]['ArrivalEHFSMDGCode'] if leg['Calls'][-1][
                                                                                                     'ArrivalEHFSMDGCode'] != '' else None),
        etd=(etd := next(led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if led['Type'] == 'ETD')),
        eta=(eta := next(lea['CallDateTime'] for lea in leg['Calls'][-1]['CallDates'] if lea['Type'] == 'ETA')),
        transitTime=int((datetime.fromisoformat(eta) - datetime.fromisoformat(etd)).days),
        cutoffs=Cutoff.model_construct(docCutoffDate=si_cutoff, cyCutoffDate=next(
            (led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if
             led.get('CallDateTime') and led['Type'] == 'CYCUTOFF'), None),
                                       vgmCutoffDate=next(
                                           (led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if
                                            led.get('CallDateTime') and led['Type'] == 'VGM'), None))
        if (si_cutoff := next((led['CallDateTime'] for led in leg['Calls'][0]['CallDates'] if
                               led['Type'] == 'SI' and led.get('CallDateTime')), None)) else None,
        transportations=Transportation.model_construct(transportType='Vessel',
                                                       transportName=leg.get('TransportationMeansName'),
                                                       referenceType='IMO' if (imo_code := leg.get(
                                                           'IMONumber')) and imo_code != '' else None,
                                                       reference=imo_code if imo_code != '' else None),
        services=Service.model_construct(serviceCode=leg['Service']['Description']) if leg.get('Service') else None,
        voyages=Voyage.model_construct(internalVoyage=leg['Voyages'][0]['Description'] if leg.get('Voyages') else None))
        for leg in leg_task]
    return leg_list


def process_schedule_data(task: dict, direct_only: bool | None, vessel_imo: str, service: str, tsp: str) -> Iterator:
    """Map the schedule and leg body"""
    check_service_code: bool = any(
        service_desc.get('Service') and service_desc['Service']['Description'] == service for service_desc in
        task['Schedules']) if service else True
    check_transshipment: bool = len(task.get('Schedules')) > 1
    transshipment_port = any(
        tsport['Calls'][0]['Code'] == tsp for tsport in task['Schedules'][1:]) if check_transshipment and tsp else False
    check_vessel_imo: bool = any(
        imo for imo in task['Schedules'] if imo.get('IMONumber') == vessel_imo) if vessel_imo else True
    if (transshipment_port or not tsp) and (
            direct_only is None or check_transshipment != direct_only) and check_service_code and check_vessel_imo:
        first_point_from: str = task['Schedules'][0]['Calls'][0]['Code']
        last_point_to: str = task['Schedules'][-1]['Calls'][-1]['Code']
        first_etd: str = next(
            ed['CallDateTime'] for ed in task['Schedules'][0]['Calls'][0]['CallDates'] if ed['Type'] == 'ETD')
        last_eta: str = next(
            ed['CallDateTime'] for ed in task['Schedules'][-1]['Calls'][-1]['CallDates'] if ed['Type'] == 'ETA')
        transit_time: int = int((datetime.fromisoformat(last_eta) - datetime.fromisoformat(first_etd)).days)
        schedule_body = Schedule.model_construct(scac='MSCU', pointFrom=first_point_from, pointTo=last_point_to,
                                                 etd=first_etd, eta=last_eta, transitTime=transit_time,
                                                 transshipment=check_transshipment,
                                                 legs=process_leg_data(leg_task=task['Schedules']))
        yield schedule_body


async def get_msc_token(client: HTTPClientWrapper, background_task: BackgroundTasks, oauth: str, aud: str, rsa: str,
                        msc_client: str, msc_scope: str, msc_thumbprint: str) -> AsyncIterator:
    x5t: bytes = b64encode(bytearray.fromhex(msc_thumbprint))
    payload_header: dict = {'x5t': x5t.decode(), 'typ': 'JWT'}
    payload_data: dict = {'aud': aud, 'iss': msc_client, 'sub': msc_client,
                          'exp': datetime.now(tz=timezone.utc) + timedelta(hours=2),
                          'nbf': datetime.now(tz=timezone.utc)}
    private_rsa_key = serialization.load_pem_private_key(b64decode(rsa), password=None, backend=default_backend())
    encoded: str = jwt.encode(headers=payload_header, payload=payload_data, key=private_rsa_key, algorithm='RS256')
    params: dict = {'scope': msc_scope, 'client_id': msc_client,
                    'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                    'grant_type': 'client_credentials', 'client_assertion': encoded}
    headers: dict = {'Content-Type': 'application/x-www-form-urlencoded'}
    response_token: dict = await anext(
        client.parse(method='POST', background_tasks=background_task, url=oauth, headers=headers, data=params,
                     namespace='msc token', expire=timedelta(minutes=50)))
    return response_token['access_token']


async def get_msc_p2p(client: HTTPClientWrapper, background_task: BackgroundTasks, url: str, oauth: str, aud: str,
                      pw: str, msc_client: str, msc_scope: str, msc_thumbprint: str, pol: str, pod: str,
                      search_range: int, start_date_type: str, start_date: datetime.date, direct_only: bool | None,
                      vessel_imo: str | None = None, service: str | None = None, tsp: str | None = None) -> Generator:
    params: dict = {'fromPortUNCode': pol, 'toPortUNCode': pod, 'fromDate': start_date.strftime('%Y-%m-%d'),
                    'toDate': (start_date + timedelta(days=search_range)).strftime("%Y-%m-%d"),
                    'datesRelated': start_date_type}
    generate_schedule = lambda data: (schedule_result for task in data['MSCSchedule']['Transactions'] for
                                      schedule_result in
                                      process_schedule_data(task=task, direct_only=direct_only, vessel_imo=vessel_imo,
                                                            service=service, tsp=tsp))
    token = await get_msc_token(client=client, background_task=background_task, oauth=oauth, aud=aud, rsa=pw,
                                msc_client=msc_client, msc_scope=msc_scope, msc_thumbprint=msc_thumbprint)
    headers: dict = {'Authorization': f'Bearer {token}'}
    response_json: dict = await anext(
        client.parse(method='GET', background_tasks=background_task, url=url, params=params, headers=headers,
                     namespace='msc original response'))
    if response_json:
        return generate_schedule(data=response_json)
