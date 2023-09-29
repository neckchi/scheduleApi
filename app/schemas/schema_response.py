import logging
from uuid import UUID
from datetime import datetime
from typing_extensions import Annotated
from pydantic import BaseModel, Field, PositiveInt,field_validator,model_validator
from pydantic.functional_serializers import PlainSerializer
from .schema_request import CarrierCode

def convert_datetime_to_iso_8601(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S')

datetime = Annotated[
    datetime, PlainSerializer(convert_datetime_to_iso_8601, return_type=str, when_used='json')
]

class PointFrom(BaseModel):
    locationName: str | None = Field(max_length=100, default=None, example='Hong Kong')
    locationCode: str = Field(max_length=5, title="Port Of Discharge", example='HKHKG', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    terminalName: str | None = Field(max_length=100, default=None, example='HONG KONG INTL TERMINAL (HIT4)')
    terminalCode: str | None = Field(default=None, example='HIT4')


class PointTo(BaseModel):
    locationName: str | None = Field(max_length=100, default=None, example='Hamburg')
    locationCode: str = Field(max_length=5, title="Port Of Discharge", example='DEHAM', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    terminalName: str | None = Field(max_length=100, default=None, example='HHLA CTT')
    terminalCode: str | None = Field(default=None, example='DEHAMCTT')


class Cutoff(BaseModel):
    bookingCutoff: datetime | None = Field(default=None)
    cyCuttoff: datetime | None = Field(default=None)
    siCuttoff: datetime | None = Field(default=None)
    vgmCutoff: datetime | None = Field(default=None)
    customsCutoff: datetime | None = Field(default=None)
    securityFilingCutoff: datetime | None = Field(default=None)


class Transportation(BaseModel):
    transportType: str = Field(description='e.g:Vessel,Barge,Feeder,Truck,Rail,Truck / Rail,Intermodal', example='Vessel')
    transportName: str | None = Field(title='Vehicle Type', description='e.g:VesselName', example='ISEACO WISDOM',default=None)
    referenceType: str | None = Field(title='Reference Type', description='e.g:IMO', example='IMO',default=None)
    reference: int | str | None = Field(title='Reference Value', description='e.g:Vessel IMO Code', example='9172301',default=None)

    @model_validator(mode = 'after')
    def check_reference_type_or_reference(self) -> 'Transportation':
        reference = self.reference
        reference_type = self.referenceType
        if (reference_type is not None and reference is not None ) or (reference_type is None and reference is None):
            return self
        logging.error(' Either both of reference type and reference existed or both are not existed ')
        raise ValueError(' Either both of reference type and reference existed or both are not existed ')

    @field_validator('transportType')
    def check_transport_type(cls, v: str) -> str:
        if v not in ('Vessel', 'Barge', 'Feeder', 'Truck', 'Rail','Truck / Rail', 'Intermodal'):
            logging.error('must contain at least one of transport type')
            raise ValueError('must contain at least one of transport type')
        return v


class Voyage(BaseModel):
    internalVoyage: str | None = Field(default=None, example='012W')
    externalVoyage: str | None = Field(default=None, example='126W')


class Service(BaseModel):
    serviceCode: str | None = Field(default=None, example='NVS')
    serviceName: str | None = Field(default=None, example='EAST ASIA TRADE')


class Leg(BaseModel):
    pointFrom: PointFrom = Field(description="This could be point/port")
    pointTo: PointTo = Field(description="This could be point/port")
    etd: datetime
    eta: datetime
    cutoffs: Cutoff | None = Field(default=None, title="A Series Of Cut Off date")
    transitTime: int = Field(ge=0, title="Leg Transit Time",
                             description="Transit Time on Leg Level")
    transportations: Transportation | None
    voyages: Voyage | None = Field(default=None, title="Voyage Number.Keep in mind that voyage number is not mandatory")
    services: Service | None = Field(default=None, title="Service Loop")
    # _check_etd_eta = root_validator(pre=True, allow_reuse=True)(check_etd_eta)

    @model_validator(mode='after')
    def check_reference_type_or_reference(self) -> 'Leg':
        etd = self.etd
        eta = self.eta
        if eta >= etd  or etd <= eta:
            return self
        logging.error('ETA must be equal  or greater than ETD.vice versa')
        raise ValueError('ETA must be equal  or greater than ETD.vice versa')

class Schedule(BaseModel):
    scac: CarrierCode = Field(max_length=4, title="Carrier Code", description="This is SCAC.It must be 4 characters",
                              example="MAEU")
    pointFrom: str = Field(max_length=5, title="First Port Of Loading", example='HKHKG', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    pointTo: str = Field(max_length=5, title="Last Port Of Discharge", example='DEHAM', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    etd: datetime
    eta: datetime
    cyCutOffDate: datetime | None = Field(default= None)
    docCutOffDate: datetime | None = Field(default= None)
    vgmCutOffDate: datetime | None = Field(default= None)
    transitTime: int = Field(ge=0, alias='transitTime', title="Schedule Transit Time",
                             description="Transit Time on Schedule Level")
    transshipment: bool = Field(title="Is transshipment?")
    legs: list[Leg] = Field(default_factory=list)
    @model_validator(mode='after')
    def check_reference_type_or_reference(self) -> 'Schedule':
        etd = self.etd
        eta = self.eta
        if eta >= etd  or etd <= eta:
            return self
        logging.error('ETA must be equal or greater than ETD.vice versa')
        raise ValueError('ETA must be equal or greater than ETD.vice versa')


class Product(BaseModel):
    productid: UUID = Field(description='Generate UUID based on the request params',
                            example='27d23af3-36be-57ce-9dbf-7813e672076c')
    origin: str = Field(max_length=5, title="Origin ",
                        description="This is the origin of country presented in UNECE standard", example="HKHKG",
                        pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    destination: str = Field(max_length=5, title="Origin ",
                             description="This is the origin of country presented in UNECE standard ", example="DEHAM",
                             pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    noofSchedule: PositiveInt = Field(title='Number Of Schedule', example=1)
    schedules: list[Schedule] | None = Field(default=None, title='Number Of Schedules',
                                             description="The number of p2p schedule offered by carrier")


class Error(BaseModel):
    id: UUID
    error: str
