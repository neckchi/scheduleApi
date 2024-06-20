from enum import Enum,StrEnum
from typing_extensions import Literal

CarrierCode = Literal['MSCU', 'CMDU', 'ANNU', 'APLU', 'CHNL', 'ONEY','HDMU','ZIMU','MAEU','MAEI','OOLU','COSU','HLCU']

CMA_GROUP: dict = {'0001': 'CMDU', '0002': 'ANNU', '0011': 'CHNL', '0015': 'APLU'}

TRANSPORT_TYPE: dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel','BAR': 'Barge', 'BCO': 'Barge', 'FEF': 'Feeder', 'FEO': 'Feeder', 'MVS': 'Vessel',
                        'RCO': 'Rail', 'RR': 'Rail', 'TRK': 'Truck', 'VSF': 'Feeder', 'VSL': 'Feeder', 'VSM': 'Vessel'}


class StartDateType(StrEnum):
    departure = "Departure"
    arrival = "Arrival"

class SearchRange(Enum):
    One = ('1', 7)
    Two = ('2', 14)
    Three = ('3', 21)
    Four = ('4', 28)

    def __new__(cls, value, days):
        member = object.__new__(cls)
        member._value_ = value
        member.duration = days
        return member




