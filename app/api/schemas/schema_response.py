import logging
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, NonNegativeInt ,model_validator,ConfigDict,TypeAdapter,AfterValidator
from .schema_request import CarrierCode
from typing import Literal,Optional,Annotated,Union,Any,List


def convert_datetime_to_iso_8601(date_string: str) -> str:
    reformat_date_string = date_string.split("+")[0] if "+" in date_string else date_string[:19]
    if "." in reformat_date_string:
        reformat_date_string = reformat_date_string.split(".")[0]
    try:
        if "T" in reformat_date_string:
            date_object = datetime.strptime(reformat_date_string, "%Y-%m-%dT%H:%M:%S")
        else:
            date_object = datetime.strptime(reformat_date_string, "%Y-%m-%d %H:%M:%S")
        return date_object.strftime('%Y-%m-%dT%H:%M:%S')
    except ValueError:
        return reformat_date_string

DateTimeReformat =  Annotated[str, AfterValidator(convert_datetime_to_iso_8601)]

class PointBase(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    locationName: Optional[Any] = None
    locationCode: Annotated[str,Field(max_length=5, title="Port Of Discharge",pattern =r"[A-Z]{2}[A-Z0-9]{3}")]
    terminalName: Optional[Any] = None
    terminalCode: Optional[Any] = None

class Cutoff(BaseModel):
    cyCutoffDate: Optional[DateTimeReformat] = None
    docCutoffDate: Optional[DateTimeReformat] = None
    vgmCutoffDate: Optional[DateTimeReformat] = None


TRANSPORT_TYPE = Literal['Vessel', 'Barge', 'Feeder', 'Truck', 'Rail', 'Truck/Rail','Road/Rail','Road','Intermodal']
REFERENCE_MAPPING: dict = {'Vessel': '1', 'Barge': '9', 'Feeder': '9', 'Truck': '3','Road': '3','Road/Rail':'11','Rail': '11', 'Truck / Rail': '11','Intermodal': '5'}
class Transportation(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    transportType: TRANSPORT_TYPE
    transportName: Optional[Any] = None
    referenceType: Optional[str] = None
    reference: Optional[Union[str, int]] = None

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
    model_config = ConfigDict(cache_strings=False)
    internalVoyage: Optional[Any] = None
    externalVoyage: Optional[Any] = None

    @model_validator(mode='after')
    def check_voyage(self) -> 'Voyage':
        if self.internalVoyage is None:
            self.internalVoyage = '001'
        return self


class Service(BaseModel):
    model_config = ConfigDict(cache_strings='all')
    serviceCode: Optional[Any] = None
    serviceName: Optional[Any] = None

class Leg(BaseModel):
    model_config = ConfigDict(cache_strings=False)
    pointFrom: PointBase
    pointTo: PointBase
    etd: DateTimeReformat
    eta: DateTimeReformat
    cutoffs: Optional[Cutoff] = None
    transitTime: NonNegativeInt
    transportations: Optional[Transportation] = None
    voyages: Voyage
    services: Optional[Service] = None

    @model_validator(mode='after')
    def check_leg_details(self) -> 'Leg':
        if self.eta < self.etd  or self.etd > self.eta:
            logging.error(f'The Leg ETA ({self.eta}) must be greater than ETD({self.etd}).vice versa')
            raise ValueError(f'The Leg ETA ({self.eta}) must be greater than ETD({self.etd}).vice versa')
        return self
    @model_validator(mode='after')
    def check_cy_cut_off(self) -> 'Leg':
        if self.cutoffs and self.cutoffs.cyCutoffDate and self.etd < self.cutoffs.cyCutoffDate:
            self.cutoffs = None
        return self

class Schedule(BaseModel):
    model_config = ConfigDict(cache_strings=False)
    scac: CarrierCode
    pointFrom: Annotated[str,Field(max_length=5, title="Port Of Loading", pattern =r"[A-Z]{2}[A-Z0-9]{3}")]
    pointTo:Annotated[str,Field(max_length=5, title="Port Of Discharge", pattern =r"[A-Z]{2}[A-Z0-9]{3}")]
    etd: DateTimeReformat
    eta: DateTimeReformat
    transitTime: NonNegativeInt
    transshipment: bool
    legs: List[Leg] = Field(default_factory=list)

    @model_validator(mode='after')
    def check_etd_eta(self) -> 'Schedule':
        if self.eta < self.etd  or self.etd > self.eta:
            logging.error(f'The Schedule ETA ({self.eta}) must be greater than ETD({self.etd}).vice versa')
            raise ValueError(f'The Schedule ETA ({self.eta}) must be greater than ETD({self.etd}).vice versa')
        return self


class Product(BaseModel):
    model_config = ConfigDict(cache_strings=False)
    productid: UUID
    origin: Annotated[str,Field(max_length=5, title="Port Of Loading",  pattern =r"[A-Z]{2}[A-Z0-9]{3}")]
    destination: Annotated[str,Field(max_length=5, title="Port Of Discharge",  pattern =r"[A-Z]{2}[A-Z0-9]{3}")]
    noofSchedule:NonNegativeInt
    schedules: Optional[List[Schedule]] = None

class Error(BaseModel):
    productid: UUID
    details: str
class HealthCheck(BaseModel):
    """Response model to validate and return when performing a health check."""
    status: str = "OK"

PRODUCT_ADAPTER = TypeAdapter(Product)


