from functools import cache

# 👇👇
"""You might have some questions about why we've done like this. its becoz we dont want each schedule & leg to be validated twice.We just want to validate all schedule once.
However, pydantic library doesnt allow user to disable validation during instance creation.Each time any instance created for schedule will get validated. this is not what we wanted.
Therefore, if you have a look at schedule.py, all schedules we got from each API call will only get validated once in th end.
On the other hands, considering state management and overhead issue, we decided to use function to deal with it for each carrier
# its becoz such mapping is just straightforward ,lightweight and stateless operations instead of creating large number of instance for each call."""

@cache
def produce_schedule_body(carrier_code:str,first_point_from:str,last_point_to:str,first_etd:str,last_eta:str,transit_time:int,
                          check_transshipment:bool,cy_cutoff:str | None = None,doc_cutoff:str | None = None,vgm_cutoff:str | None = None) -> dict:
    schedule_body: dict = {'scac': carrier_code,
                           'pointFrom': first_point_from,
                           'pointTo': last_point_to,
                           'etd': first_etd,
                           'eta': last_eta,
                           'transitTime': transit_time,
                           'cyCutOffDate':cy_cutoff,'docCutOffDate':doc_cutoff ,'vgmCutOffDate': vgm_cutoff,
                           'transshipment': check_transshipment
                           }
    return schedule_body
@cache
def produce_leg_body(origin_un_code:str,dest_un_code:str,etd:str,eta:str,
                   tt:int,origin_un_name:str|None = None,dest_un_name:str|None = None,origin_term_name:str|None = None,origin_term_code:str|None = None,
                    dest_term_name:str|None = None,dest_term_code:str|None = None,cy_cutoff:str = None,si_cutoff:str|None = None,doc_cutoff:str|None = None,vgm_cutoff:str|None = None,
                   transport_type:str|None= None,transport_name:str|None= None,reference_type:str|None= None,reference:str|None = None,
                     internal_voy:str|None= None,external_voy:str|None = None,service_code:str|None = None,service_name:str|None = None) -> dict:
    leg_body: dict = {
        'pointFrom': {'locationName': origin_un_name,
                      'locationCode': origin_un_code,
                      'terminalName': origin_term_name,
                      'terminalCode': origin_term_code
                      },
        'pointTo': {'locationName': dest_un_name,
                    'locationCode': dest_un_code,
                    'terminalName': dest_term_name,
                    'terminalCode': dest_term_code
                    },
        'etd': etd,
        'eta': eta,
        'transitTime': tt,
        'transportations': {
            'transportType': transport_type,
            'transportName': transport_name,
            'referenceType': reference_type,
            'reference': reference
        }
    }

    if cy_cutoff or doc_cutoff or vgm_cutoff or si_cutoff:
        leg_body.update({"cutoffs": {
            'cyCuttoff': cy_cutoff,
            'siCuttoff':si_cutoff,
            'docCutOffDate':doc_cutoff,
            'vgmCutOffDate':vgm_cutoff
        }})

    if internal_voy or external_voy:
        leg_body.update({'voyages': {
            'internalVoyage': internal_voy,
            'externalVoyage':external_voy
        }})
    if service_code or service_name:
        leg_body.update({'services': {
            'serviceCode': service_code,
            'serviceName':service_name
        }})
    return leg_body
#
#
def produce_schedule(schedule:dict,legs:list[dict])->dict:
    schedule.update({'legs':legs})
    return schedule