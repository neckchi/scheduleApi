from typing import Literal, Optional, Annotated, Any, List
from enum import Enum, StrEnum
from pydantic import BaseModel, Field, TypeAdapter
from datetime import date

CarrierCode = Literal[
    'MSCU', 'CMDU', 'ANNU', 'APLU', 'CHNL', 'ONEY', 'HDMU', 'ZIMU', 'MAEU', 'MAEI', 'OOLU', 'COSU', 'HLCU']


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


class QueryParams(BaseModel):
    model_config = {"extra": "forbid"}
    point_from: Annotated[str, Field(validation_alias="pointFrom", serialization_alias="pointFrom", max_length=5,
                                     description="Port Of Loading", pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    point_to: Annotated[str, Field(validation_alias="pointTo", serialization_alias="pointTo", max_length=5,
                                   description="Port Of Discharge", pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    start_date_type: Annotated[
        StartDateType, Field(validation_alias="startDateType", serialization_alias="startDateType",
                             description="Search by either ETD or ETA")]
    start_date: Annotated[
        date, Field(validation_alias="startDate", serialization_alias="startDate", description='YYYY-MM-DD')]
    search_range: Annotated[SearchRange, Field(validation_alias='searchRange', serialization_alias='searchRange',
                                               description='Search range based on start date and type,max 4 weeks')]
    scac: Annotated[List[CarrierCode | None], Field(default=[None])]
    direct_only: Annotated[
        Optional[bool], Field(validation_alias='directOnly', serialization_alias='directOnly', default=None,
                              description='Direct means only show direct schedule Else show both(direct/transshipment)type of schedule')]
    tsp: Annotated[
        Optional[str], Field(validation_alias='transhipmentPort', serialization_alias='transhipmentPort', max_length=5,
                             default=None, description="Port Of Transshipment", pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    vessel_imo: Annotated[
        Optional[str], Field(validation_alias='vesselIMO', serialization_alias='vesselIMO', default=None,
                             description='Restricts the search to a particular vessel IMO lloyds code on port of loading',
                             max_length=7)]
    vessel_flag_code: Annotated[
        Optional[str], Field(validation_alias='vesselFlagCode', serialization_alias='vesselFlagCode', default=None,
                             description="vessel flag", max_length=2, pattern=r"[A-Z]{2}"),]
    service: Annotated[Any, Field(validation_alias='service', serialization_alias='service', default=None,
                                  description="service code or service name")]


class PortCodeMapping(BaseModel):
    scac: CarrierCode
    kn_port_code: Annotated[str, Field(max_length=5, title="kn port code", pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    carrier_port_code: Annotated[str, Field(max_length=5, title="carrier port code", pattern=r"[A-Z]{2}[A-Z0-9]{3}")]


PORT_CODE_ADAPTER = TypeAdapter(List[PortCodeMapping])
