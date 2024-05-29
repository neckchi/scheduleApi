import logging
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, PositiveInt,model_validator,ConfigDict
from .schema_request import CarrierCode
from typing_extensions import Literal
from functools import lru_cache


@lru_cache(maxsize=128)
def convert_datetime_to_iso_8601(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M:%S')

class PointBase(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    locationName: str | None = Field(max_length=100, default=None, example='Hong Kong')
    locationCode: str = Field(max_length=5, title="Port Of Discharge", example='HKHKG', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    terminalName: str | None = Field(max_length=100, default=None, example='HONG KONG INTL TERMINAL (HIT4)')
    terminalCode: str | None = Field(default=None, example='HIT4')


class Cutoff(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: convert_datetime_to_iso_8601})
    cyCutoffDate: datetime | None = Field(default=None,example='2023-11-11T22:00:00')
    docCutoffDate: datetime | None = Field(default=None,example='2023-11-11T22:00:00')
    vgmCutoffDate: datetime | None = Field(default=None,example='2023-11-11T22:00:00')


TRANSPORT_TYPE = Literal['Vessel', 'Barge', 'Feeder', 'Truck', 'Rail', 'Truck / Rail','Intermodal']
REFERENCE_MAPPING: dict = {'Vessel': '1', 'Barge': '9', 'Feeder': '9', 'Truck': '3', 'Rail': '11', 'Truck / Rail': '11','Intermodal': '5'}
class Transportation(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    transportType: TRANSPORT_TYPE = Field(description='e.g:Vessel,Barge,Feeder,Truck,Rail,Truck / Rail,Intermodal', example='Vessel')
    transportName: str | None = Field(title='Vehicle Type',max_length=40, description='e.g:VesselName', example='ISEACO WISDOM',default=None)
    referenceType: str | None = Field(title='Reference Type', description='e.g:IMO', example='IMO',default=None)
    reference: int | str | None = Field(title='Reference Value', description='e.g:Vessel IMO Code', example='9172301',default=None)

    @model_validator(mode = 'after')
    def check_reference_type_or_reference(self) -> 'Transportation':
        reference = self.reference
        reference_type = self.referenceType
        if (reference_type is  None and reference is not None) or (reference_type is not None and reference is None):
            logging.error(' Either both of reference type and reference existed or both are not existed ')
            raise ValueError(f'Either both of reference type and reference existed or both are not existed')
        return self

    @model_validator(mode = 'after')
    def add_reference(self)-> 'Transportation':
        if self.referenceType is None and self.reference is None and self.transportType is not None:
            self.transportName = 'TBN' if self.transportName is None else self.transportName
            self.referenceType = 'IMO'
            self.reference = REFERENCE_MAPPING.get(self.transportType)
        return self


class Voyage(BaseModel):
    internalVoyage: str | None = Field(default=None,max_length=10, example='126W')
    externalVoyage: str | None = Field(default=None,max_length=10, example='126W')
    @model_validator(mode='after')
    def check_voyage(self) -> 'Voyage':
        if self.internalVoyage is None:
            self.internalVoyage = '001'
        return self

class Service(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    serviceCode: str | None = Field(default=None,max_length=100, example='NVS')
    serviceName: str | None = Field(default=None,max_length=100, example='EAST ASIA TRADE')



class Leg(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: convert_datetime_to_iso_8601})
    pointFrom: PointBase = Field(description="This could be point/port")
    pointTo: PointBase = Field(description="This could be point/port")
    etd: datetime = Field(example='2023-11-13T18:00:00')
    eta: datetime = Field(example='2023-12-15T07:00:00')
    cutoffs: Cutoff | None = Field(default=None, title="A Series Of Cut Off date")
    transitTime: int = Field(ge=0, title="Leg Transit Time",
                             description="Transit Time on Leg Level",example='31')
    transportations: Transportation | None
    voyages: Voyage = Field(title="Voyage Number.Keep in mind that voyage number is mandatory")
    services: Service | None = Field(default=None, title="Service Loop")
    @model_validator(mode='after')
    def check_leg_details(self) -> 'Leg':
        if self.eta < self.etd  or self.etd > self.eta:
            logging.error('ETA must be equal  or greater than ETD.vice versa')
            raise ValueError(f'ETA must be equal  or greater than ETD.vice versa')
        return self
    @model_validator(mode='after')
    def check_cy_cut_off(self) -> 'Leg':
        if self.cutoffs and self.cutoffs.cyCutoffDate and self.etd < self.cutoffs.cyCutoffDate:
            self.cutoffs = None
        return self

class Schedule(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: convert_datetime_to_iso_8601})
    scac: CarrierCode = Field(max_length=4, title="Carrier Code", description="This is SCAC.It must be 4 characters",
                              example="MAEU")
    pointFrom: str = Field(max_length=5, title="First Port Of Loading", example='HKHKG', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    pointTo: str = Field(max_length=5, title="Last Port Of Discharge", example='DEHAM', pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    etd: datetime = Field(example='2023-11-13T18:00:00')
    eta: datetime = Field(example='2023-12-15T07:00:00')
    transitTime: int = Field(ge=0, alias='transitTime', title="Schedule Transit Time",
                             description="Transit Time on Schedule Level")
    transshipment: bool = Field(title="Is transshipment?",example=False)
    legs: list[Leg] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_etd_eta(self) -> 'Schedule':
        if self.eta < self.etd  or self.etd > self.eta:
            logging.error('ETA must be equal  or greater than ETD.vice versa')
            raise ValueError(f'ETA must be equal  or greater than ETD.vice versa')
        return self


class Product(BaseModel):
    productid: UUID = Field(description='Generate UUID based on the request params',
                            example='27d23af3-36be-57ce-9dbf-7813e672076c')
    origin: str = Field(max_length=5, title="Origin ",
                        description="This is the origin of country presented in UNECE standard", example="HKHKG",
                        pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    destination: str = Field(max_length=5, title="Origin ",
                             description="This is the origin of country presented in UNECE standard ", example="DEHAM",
                             pattern =r"[A-Z]{2}[A-Z0-9]{3}")
    noofSchedule: PositiveInt = Field(ge=0,title='Number Of Schedule', example=1)
    schedules: list[Schedule] | None = Field(default=None, title='Number Of Schedules',
                                             description="The number of p2p schedule offered by carrier")


class Error(BaseModel):
    id: UUID
    detail: str
