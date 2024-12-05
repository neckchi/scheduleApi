from datetime import datetime


async def get_sudu_p2p(client, url: str, pw: str, pol: str, pod: str, direct_only: bool |None = None , tsp: str | None = None,
                       start_date:datetime.date = None,
                       date_type: str | None = None, scac: str | None = None):
    params: dict = {'from': pol, 'to': pod, 'searchDate': start_date,'dateQualifier': date_type}
    params.update({'directOnly': direct_only}) if direct_only is not None else...
    params.update({'scac': scac})if scac else ...
    headers: dict = {'x-api-key': pw}
    response = await anext(client.parse(client=client, method='GET', url=url, params=params,headers=headers))
            # Performance Enhancement - No meomory is used: async generator object - schedules
    async def schedules():
        """
        At the moment HamburgSud doenst allow any request to search for the past schedule.Otherwise, it will return 400 Bad Request
        """
        if response.status_code == 200:
            response_json:dict = response.json()
            for task in response_json:
                check_transshipment: bool = True if len(task['leg']) > 1 else False
                transshipment_port: bool = next((True for tsport in task['leg'][1:] if tsport['from']['unlocode'] == tsp),False) if check_transshipment and tsp else False
                if transshipment_port or not tsp:
                    carrier_code:str = task['products']['scac'][0]
                    transit_time:int = task['routing']['totalTransitTime']
                    first_point_from:str = task['leg'][0]['from']['unlocode']
                    last_point_to:str = task['leg'][-1]['to']['unlocode']
                    first_etd:str = task['leg'][0]['expectedDepartureLT']
                    last_eta:str = task['leg'][-1]['expectedArrivalLT']
                    first_cy_cutoff:str = next((cyc['cargoCutOffLT'] for cyc in task['leg'] if cyc['cargoCutOffLT'] is not None), None)
                    schedule_body: dict = {'scac': carrier_code, 'pointFrom': first_point_from,
                                           'pointTo': last_point_to, 'etd': first_etd, 'eta': last_eta,
                                           'cyCutOffDate': first_cy_cutoff,
                                           'transitTime': transit_time,
                                           'transshipment': check_transshipment}

                    # Performance Enhancement - No meomory is used:async generator object - schedule leg
                    async def schedule_leg():
                        for legs in task['leg']:
                            vessel_imo  = legs['vessel'].get('imo')
                            vessel_name:str = legs['vessel'].get('name')
                            from_terminal_name:str = legs['from'].get('facilityName')
                            from_terminal_code:str = legs['from'].get('facilityCode')
                            to_terminal_name:str = legs['to'].get('facilityName')
                            to_terminal_code:str = legs['to'].get('facilityCode')
                            leg_body: dict = {'pointFrom': {'locationCode': legs['from']['unlocode'],
                                                            'terminalName': from_terminal_name if from_terminal_name !='' else None,
                                                            'terminalCode': from_terminal_code if from_terminal_code !='' else None
                                                            },
                                              'pointTo': {'locationCode': legs['to']['unlocode'],
                                                          'terminalName': to_terminal_name if to_terminal_name !='' else None,
                                                          'terminalCode': to_terminal_code if to_terminal_code !='' else None
                                                          },
                                              'etd': legs['expectedDepartureLT'], 'eta': legs['expectedArrivalLT'],
                                              'transitTime': int((datetime.fromisoformat(legs['expectedArrivalLT'][:10]) - datetime.fromisoformat(legs['expectedDepartureLT'][:10])).days),
                                              'transportations': {
                                                  'transportType': 'Vessel' if legs['transportMode'] == 'Liner' else str(legs['transportMode']).title(),
                                                  'transportName': vessel_name if vessel_name !='' else None,
                                                  'referenceType': 'IMO' if vessel_imo else None,
                                                  'reference': vessel_imo if vessel_imo != '' else None
                                                                }
                                              }
                            if legs.get('cargoCutOffLT', None):
                                cut_off_body:dict = {'cyCuttoff': legs['cargoCutOffLT']}
                                leg_body.update({'cutoffs': cut_off_body})

                            if legs['vessel'].get('voyage', None):
                                voyage_body:dict = {'internalVoyage': legs['vessel']['voyage']}
                                leg_body.update({'voyages': voyage_body})

                            yield leg_body

                    schedule_body.update({'legs': [sl async for sl in schedule_leg()]})
                    yield schedule_body
                else:
                    pass
        else:pass

    return [s async for s in schedules()]

