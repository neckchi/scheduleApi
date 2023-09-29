from httpx import AsyncClient,Timeout
from app.carrierp2p.helpers import deepget,check_loop
import orjson #Orjson is built in RUST, its performing way better than python in built json
import asyncio
import os
import pytest
import logging
import csv
import datetime


logger = logging.getLogger(__name__)
this_folder = os.path.dirname(os.path.abspath(__file__))
load_test_file = os.path.join(this_folder, 'verified network/bass_p2p_portpairs.csv')
service_loop_file = os.path.join(this_folder, 'verified network/service_loop.csv')
write_test_results = os.path.join(this_folder, 'verified network/adhoc_results.csv')

sem = asyncio.Semaphore(30)#Control the number of thread by 20 as we have mutiple apps using the same API end point.it will easily exceeded the given API rate limit
timeout = Timeout(50.0, read=None, connect=60.0)


async def get_p2p(scac: str, pol: str, pod: str):
    async with sem:
        await asyncio.sleep(10)
        async with AsyncClient(base_url='http://127.0.0.1:8000', timeout=timeout) as client:
            params: dict = {'pointFrom': pol, 'pointTo': pod, 'startDateType': 'Departure','startDate': datetime.datetime.now().strftime("%Y-%m-%d"), 'searchRange': '4', 'scac': scac}
            response = await client.get(url="/schedules/p2p", params=params)
            return response

@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_schedule(anyio_backend):
    logger.info('Start p2p load test')
    passed_schedule: int = 0
    ## Getting transshipment hub and service combination from most popular portpair
    with open(load_test_file, mode="r") as p2p_file,open(write_test_results,mode="w",newline='',encoding='utf-8') as output_file:
        tasks: set = {asyncio.create_task(get_p2p(*p2p.strip().split(','))) for p2p in p2p_file.readlines()}
        gather_tasks = await asyncio.gather(*tasks)
        count_schedule: int = len(tasks)
        logger.info(f'Total Number Of Requests : {count_schedule}')
        seen:set = set() # check duplicate,only store different transshipment hub and service code for the same portpair
        csv_file = csv.DictWriter(output_file,delimiter=',',fieldnames=['CARRIER','ORIGIN','DESTINATION','TS1','LEG0'])
        csv_file.writeheader()
        for p2p_response in gather_tasks:
            if p2p_response.status_code in (200, 206):
                response = orjson.loads(p2p_response.read())
                # check_tsp:bool = next((True for schedule in response['schedules'] if schedule.get('transshipment',False)),False)
                # if check_tsp:
                #     assert check_tsp
                passed_schedule += 1
                logger.info(f'Successful:{p2p_response.status_code}-{p2p_response.json()["productid"]} ==> {p2p_response.request.url.params}')
                for schedule in response['schedules']:
                    scac: str = schedule.get('scac')
                    first_pol: str = schedule.get('pointFrom')
                    last_pod: str = schedule.get('pointTo')
                    # the transshipment port must be a seaport
                    # tsp: list = [legs['pointTo']['locationCode'] for legs in schedule['legs'] if legs['pointTo']['locationCode'] != last_pod and legs['transportations']['transportType'] in ('Vessel', 'Barge', 'Feeder','Intermodal')]
                    tsp: list = [legs['pointTo']['locationCode'] for legs in schedule['legs'] if legs['pointTo']['locationCode'] != last_pod and legs['pointFrom']['locationCode'] != legs['pointTo']['locationCode']]
                    # if tsp: #only the schedule with transshipment port will be going on with the following codes
                        # service_code:list = [legs['services'].get('serviceCode') if deepget(legs, 'services', 'serviceCode') and deepget(legs, 'transportations', 'transportType') else deepget(legs,'transportations','transportType') for legs in schedule['legs']]
                        # service_name:list = [legs['services'].get('serviceName') if deepget(legs, 'services', 'serviceName') and deepget(legs, 'transportations', 'transportType') else deepget(legs,'transportations','transportType') for legs in schedule['legs']]
                    service_code:list = [legs['services'].get('serviceCode') if legs['pointFrom']['locationCode'] != legs['pointTo']['locationCode'] and deepget(legs, 'services', 'serviceCode') and deepget(legs, 'transportations', 'transportType')
                                                                                and check_loop(file_path = service_loop_file,scac = scac,loop_code = legs['services'].get('serviceCode')) else '' for legs in schedule['legs']]

                    service_name:list = [legs['services'].get('serviceName') if legs['pointFrom']['locationCode'] != legs['pointTo']['locationCode'] and deepget(legs, 'services', 'serviceName') and deepget(legs, 'transportations', 'transportType')
                                                                                and check_loop(file_path = service_loop_file,scac = scac, loop_name = legs['services'].get('serviceName'))
                                                                                else '' for legs in schedule['legs']]

                    logger.info(f'SCAC:{scac},POL:{first_pol},POD:{last_pod},TSP(s):{tsp},Service Code(s):{service_name if scac in ("MAEU", "SEAU", "SEJJ", "MCPU", "MAEI","MSCU") else service_code}')
                    result = orjson.dumps({'CARRIER': scac, 'ORIGIN': first_pol, 'DESTINATION': last_pod, 'TS1': ';'.join(map(str, tsp)), 'LEG0': ';'.join(map(str, service_name if scac in ('MAEU', 'SEAU', 'SEJJ', 'MCPU', 'MAEI','MSCU') else service_code))})
                    if result in seen:
                        continue  # skip duplicate
                    else:
                        csv_file.writerow(orjson.loads(result))
                        seen.add(result)
                    # else:pass

                # else:
                #     assert not check_tsp
                #     logger.info(f'No transshipment schedule Found:{p2p_response.status_code}-{p2p_response.request.url.params}')
            else:
                assert p2p_response.status_code not in (200, 206)
                logger.info(f'Not Found:{p2p_response.status_code}-{p2p_response.request.url.params}')
        logger.info(f'Passing Rate : {(passed_schedule / count_schedule) * 100}%')
        logger.info('End  p2p load test')
