from enum import Enum,StrEnum
from typing_extensions import Literal

CarrierCode = Literal['MSCU', 'CMDU', 'ANNU', 'APLU', 'CHNL', 'ONEY','HDMU','ZIMU','MAEU','MAEI','OOLU','COSU','HLCU']
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




