from enum import Enum,Flag, auto


class StartDateType(str, Enum):
    departure = "Departure"
    arrival = "Arrival"

class CarrierCode(str,Enum):
    MSCU = 'MSCU'
    CMDU = 'CMDU'
    ANNU = 'ANNU'
    APLU = 'APLU'
    CHNL = 'CHNL'
    CSFU = 'CSFU'
    ONEY = 'ONEY'
    HDMU = 'HDMU'
    ZIMU = 'ZIMU'
    MAEU = 'MAEU'
    SEAU = 'SEAU'
    SEJJ = 'SEJJ'
    MCPU = 'MCPU'
    MAEI = 'MAEI'
    OOLU = 'OOLU'
    COSU = 'COSU'
    HLCU = 'HLCU'
    # SUDU = 'SUDU'
    # ANRM = 'ANRM'

    def __str__(self):
        return str(self.name)

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




