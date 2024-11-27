import asyncio

from fastapi import BackgroundTasks

from app.background_tasks import db
from app.carrierp2p.helpers import deepget
from app.routers.router_config import HTTPClientWrapper
from app.schemas.schema_response import (
    Schedule,
    Leg,
    PointBase,
    Voyage,
    Cutoff,
    Service,
    Transportation,
)
from app.schemas.schema_request import CMA_GROUP
from datetime import datetime
from typing import Generator, Iterator

DEFAULT_ETD_ETA = datetime.now().astimezone().replace(microsecond=0).isoformat()


def extract_transportation(transportation: dict):
    """Map the transportation Details"""
    mean_of_transport: str = "/".join(
        part.strip()
        for part in str(transportation["meanOfTransport"]).title().split("/")
    )
    vehicule: dict = transportation.get("vehicule", {})
    vessel_imo: str = vehicule.get("reference")
    vehicule_type: str = vehicule.get("vehiculeType")
    reference_type: str | None = None
    reference: str | None = None
    if vessel_imo and len(vessel_imo) < 9:
        reference_type: str = "IMO"
        reference: str = vessel_imo
    elif vehicule_type == "Barge":
        reference_type: str = "IMO"
        reference: str = "9"
    return Transportation.model_construct(
        transportType=mean_of_transport,
        transportName=vehicule.get("vehiculeName"),
        referenceType=reference_type,
        reference=reference,
    )


def process_leg_data(leg_task: list) -> list:
    leg_list: list = [
        Leg.model_construct(
            pointFrom=PointBase.model_construct(
                locationName=leg["pointFrom"]["location"]["name"],
                locationCode=leg["pointFrom"]["location"].get("internalCode") or leg["pointFrom"]["location"]["locationCodifications"][0]["codification"],
                terminalName=deepget(leg["pointFrom"]["location"], "facility", "name"),
                terminalCode=(
                    check_pol_terminal[0].get("codification")
                    if (
                        check_pol_terminal := deepget(
                            leg["pointFrom"]["location"],
                            "facility",
                            "facilityCodifications",
                        )
                    )
                    else None
                ),
            ),
            pointTo=PointBase.model_construct(
                locationName=leg["pointTo"]["location"]["name"],
                locationCode=leg["pointTo"]["location"].get("internalCode") or leg["pointTo"]["location"]["locationCodifications"][0]["codification"],
                terminalName=deepget(leg["pointTo"]["location"], "facility", "name"),
                terminalCode=(
                    check_pod_terminal[0].get("codification")
                    if (
                        check_pod_terminal := deepget(
                            leg["pointTo"]["location"],
                            "facility",
                            "facilityCodifications",
                        )
                    )
                    else None
                ),
            ),
            etd=leg["pointFrom"].get("departureDateGmt", DEFAULT_ETD_ETA),
            eta=leg["pointTo"].get("arrivalDateGmt", DEFAULT_ETD_ETA),
            transitTime=leg.get("legTransitTime", 0),
            transportations=extract_transportation(leg["transportation"]),
            services=(
                Service.model_construct(serviceCode=service_name)
                if (
                    service_name := deepget(
                        leg["transportation"], "voyage", "service", "code"
                    )
                )
                else None
            ),
            voyages=Voyage.model_construct(
                internalVoyage=(
                    voyage_num
                    if (
                        voyage_num := deepget(
                            leg["transportation"], "voyage", "voyageReference"
                        )
                    )
                    else None
                )
            ),
            cutoffs=(
                Cutoff.model_construct(
                    docCutoffDate=deepget(
                        leg["pointFrom"]["cutOff"],
                        "shippingInstructionAcceptance",
                        "gmt",
                    ),
                    cyCutoffDate=deepget(
                        leg["pointFrom"]["cutOff"], "portCutoff", "gmt"
                    ),
                    vgmCutoffDate=deepget(leg["pointFrom"]["cutOff"], "vgm", "gmt"),
                )
                if leg["pointFrom"].get("cutOff")
                else None
            ),
        )
        for leg in leg_task
    ]
    return leg_list


def process_schedule_data(
        task: dict,
        direct_only: bool | None,
        service_filter: str | None,
        vessel_imo_filter: str | None,
) -> Iterator:
    """Map the schedule and leg body"""
    transit_time: int = task["transitTime"]
    first_point_from: str = (
        task["routingDetails"][0]["pointFrom"]["location"].get("internalCode") or task["routingDetails"][0]["pointFrom"]["location"]["locationCodifications"][0]["codification"]
    )
    last_point_to: str = (
        task["routingDetails"][-1]["pointTo"]["location"].get("internalCode") or task["routingDetails"][-1]["pointTo"]["location"]["locationCodifications"][0]["codification"]
    )
    first_etd = next(
        (
            ed["pointFrom"]["departureDateLocal"]
            for ed in task["routingDetails"]
            if ed["pointFrom"].get("departureDateLocal")
        ),
        DEFAULT_ETD_ETA,
    )
    last_eta = next(
        (
            ea["pointTo"]["arrivalDateLocal"]
            for ea in task["routingDetails"][::-1]
            if ea["pointTo"].get("arrivalDateLocal")
        ),
        DEFAULT_ETD_ETA,
    )
    check_transshipment: bool = len(task["routingDetails"]) > 1
    check_service_code: bool = (
        any(
            leg
            for leg in task["routingDetails"]
            if deepget(leg["transportation"], "voyage", "service", "code") == service_filter
        )
        if service_filter
        else True
    )
    check_vessel_imo: bool = (
        any(
            leg
            for leg in task["routingDetails"]
            if deepget(leg["transportation"], "vehicule", "reference") == vessel_imo_filter
        )
        if vessel_imo_filter
        else True
    )
    if (
            (direct_only is None or direct_only != check_transshipment) and check_vessel_imo and check_service_code
    ):
        schedule_body = Schedule.model_construct(
            scac=CMA_GROUP.get(task["shippingCompany"]),
            pointFrom=first_point_from,
            pointTo=last_point_to,
            etd=first_etd,
            eta=last_eta,
            transitTime=transit_time,
            transshipment=check_transshipment,
            legs=process_leg_data(leg_task=task["routingDetails"]),
        )
        yield schedule_body


async def fetch_additional_schedules(
        client: HTTPClientWrapper, url: str, headers: dict, params: dict, awaited_response
) -> list:
    """Fetch additional schedules if the initial response indicates more data is available (HTTP 206)."""
    page: int = 50
    last_page: int = int(awaited_response.headers["content-range"].partition("/")[2])
    cma_code_header: str = awaited_response.headers["X-Shipping-Company-Routings"]
    check_header: bool = len(cma_code_header.split(",")) > 1

    def updated_params(cma_internal_code):
        return {
            **params,
            **{
                **(
                    {"shippingCompany": cma_internal_code}
                    if cma_internal_code is not None
                    else {}
                ),
                "specificRoutings": "Commercial",
            },
        }

    extra_tasks: list = [
        asyncio.create_task(
            anext(
                client.parse(
                    scac="cma",
                    method="GET",
                    url=url,
                    params=(
                        updated_params(cma_code_header)
                        if not check_header
                        else dict(params, **{"specificRoutings": "Commercial"})
                    ),
                    headers=dict(headers, **{"range": f"{num}-{49 + num}"}),
                )
            )
        )
        for num in range(page, last_page, page)
    ]
    additional_schedules: list = []
    for extra_p2p in asyncio.as_completed(extra_tasks):
        result = await extra_p2p
        if result:
            additional_schedules.extend(await result.json())
    return additional_schedules


async def fetch_initial_schedules(
        client: HTTPClientWrapper,
        cma_list: list,
        url: str,
        headers: dict,
        params: dict,
        extra_condition: bool,
) -> list:
    """Fetch the initial set of schedules from CMA."""

    def updated_params(cma_internal_code):
        return {
            **params,
            **(
                {"shippingCompany": cma_internal_code}
                if cma_internal_code is not None
                else {}
            ),
            "specificRoutings": (
                "USGovernment"
                if cma_internal_code == "0015" and extra_condition
                else "Commercial"
            ),
        }

    p2p_resp_tasks: list = [
        asyncio.create_task(
            anext(
                client.parse(
                    scac="cma",
                    method="GET",
                    url=url,
                    params=updated_params(cma_code),
                    headers=headers,
                )
            )
        )
        for cma_code in cma_list
    ]
    all_schedule: list = []
    for response in asyncio.as_completed(p2p_resp_tasks):
        awaited_response = await response
        check_extension = (
            awaited_response is not None and not isinstance(awaited_response,
                                                            list) and awaited_response.status == 206
        )
        if awaited_response:
            all_schedule.extend(
                await awaited_response.json() if check_extension else awaited_response
            )
            if check_extension:
                all_schedule.extend(
                    await fetch_additional_schedules(
                        client, url, headers, params, awaited_response
                    )
                )
    return all_schedule


async def get_cma_p2p(
        client: HTTPClientWrapper,
        background_task: BackgroundTasks,
        url: str,
        pw: str,
        pol: str,
        pod: str,
        search_range: int,
        direct_only: bool | None,
        tsp: str | None = None,
        vessel_imo: str | None = None,
        service: str | None = None,
        departure_date: datetime.date = None,
        arrival_date: datetime.date = None,
        scac: str | None = None,
) -> Generator:
    api_carrier_code: str = (
        next(k for k, v in CMA_GROUP.items() if v == scac.upper()) if scac else None
    )
    headers: dict = {"keyID": pw}
    carrier_params: dict = {
        "placeOfLoading": pol,
        "placeOfDischarge": pod,
        "departureDate": departure_date,
        "searchRange": search_range,
        "arrivalDate": arrival_date,
        "tsPortCode": tsp,
    }
    params: dict = {
        k: v for k, v in carrier_params.items() if v is not None
    }  # Remove the key if its value is None
    extra_condition: bool = pol.startswith("US") and pod.startswith("US")
    cma_list: list = [None, "0015"] if api_carrier_code is None else [api_carrier_code]
    response_cache = await db.get(scac='cma_group' if api_carrier_code is None else api_carrier_code,
                                  params=params | {'scac_group': api_carrier_code}, original_response=True,
                                  log_component='cma original response file')
    if response_cache:
        return (
            schedule_result
            for task in response_cache
            for schedule_result in process_schedule_data(
                task=task,
                direct_only=direct_only,
                service_filter=service,
                vessel_imo_filter=vessel_imo,
            )
        )
    response_json = await fetch_initial_schedules(
        client=client,
        url=url,
        headers=headers,
        params=params,
        cma_list=cma_list,
        extra_condition=extra_condition,
    )
    if response_json:
        background_task.add_task(db.set, scac='cma_group' if api_carrier_code is None else api_carrier_code,
                                 params=params | {'scac_group': api_carrier_code}, original_response=True,
                                 value=response_json, log_component='cma original response file')
        return (
            schedule_result
            for task in response_json
            for schedule_result in process_schedule_data(
                task=task,
                direct_only=direct_only,
                service_filter=service,
                vessel_imo_filter=vessel_imo,
            )
        )
