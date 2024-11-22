from datetime import datetime, date
from enum import Enum, StrEnum
from typing import Literal, Optional, Annotated, Any, List

from pydantic import BaseModel, Field

CarrierCode = Literal[
    'MSCU', 'CMDU', 'ANNU', 'APLU', 'CHNL', 'ONEY', 'HDMU', 'ZIMU', 'MAEU', 'MAEI', 'OOLU', 'COSU', 'HLCU']

CMA_GROUP: dict = {'0001': 'CMDU', '0002': 'ANNU', '0011': 'CHNL', '0015': 'APLU'}

TRANSPORT_TYPE: dict = {'Land Trans': 'Truck', 'Feeder': 'Feeder', 'TO BE NAMED': 'Vessel', 'BAR': 'Barge',
                        'BCO': 'Barge', 'FEF': 'Feeder', 'FEO': 'Feeder', 'MVS': 'Vessel',
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


class QueryParams(BaseModel):
    model_config = {"extra": "forbid"}
    point_from: Annotated[str, Field(validation_alias="pointFrom", serialization_alias="pointFrom", max_length=5,
                                     description="Port Of Loading", example='HKHKG', pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    point_to: Annotated[str, Field(validation_alias="pointTo", serialization_alias="pointTo", max_length=5,
                                   description="Port Of Discharge", example='DEHAM', pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    start_date_type: Annotated[
        StartDateType, Field(validation_alias="startDateType", serialization_alias="startDateType",
                             description="Search by either ETD or ETA")]
    start_date: Annotated[
        date, Field(validation_alias="startDate", serialization_alias="startDate", description='YYYY-MM-DD',
                    example=datetime.now().strftime("%Y-%m-%d"))]
    search_range: Annotated[SearchRange, Field(validation_alias='searchRange', serialization_alias='searchRange',
                                               description='Search range based on start date and type,max 4 weeks',
                                               examples=SearchRange.Three.duration)]
    scac: List[CarrierCode | None] = [None]

    direct_only: Annotated[
        Optional[bool], Field(validation_alias='directOnly', serialization_alias='directOnly', default=None,
                              description='Direct means only show direct schedule Else show both(direct/transshipment)type of schedule')]
    tsp: Annotated[Optional[str], Field(validation_alias='transhipmentPort', serialization_alias='transhipmentPort', max_length=5, default=None,
                                        description="Port Of Transshipment", example='SGSIN',
                                        pattern=r"[A-Z]{2}[A-Z0-9]{3}")]
    vessel_imo: Annotated[
        Optional[str], Field(validation_alias='vesselIMO', serialization_alias='vesselIMO', default=None,
                             description='Restricts the search to a particular vessel IMO lloyds code on port of loading',
                             max_length=7)]
    vessel_flag_code: Annotated[
        Optional[str], Field(validation_alias='vesselFlagCode', serialization_alias='vesselFlagCode', default=None,
                             description="vessel flag", max_length=2, pattern=r"[A-Z]{2}")]
    service: Annotated[Any, Field(validation_alias='service', serialization_alias='service', default=None,
                                  description="service code or service name")]
