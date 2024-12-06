import csv
import io
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.schemas.schema_request import CarrierCode, PORT_CODE_ADAPTER, PortCodeMapping
from app.internal.security import basic_auth
from app.storage import db

router = APIRouter(prefix='/portmapping', tags=["Port Code Mapping"], dependencies=[Depends(basic_auth)])


@router.post("/upload", summary="Upload port code mapping information")
async def upload_port_code_mapping(upload_file: UploadFile):
    """
    CSV files must have 3 columns:
    - **scac** : Provide carrier code that you would like to convert the requested port code to carrier port code
    - **kn_port_code** : Provide kn port code that you usually request from API hub and would like to convert it to carrier port code
    - **carrier_port_code** : Provide carrier port code.This code is what we endup using for API request.
    """
    chunk_size: int = 1024
    try:
        chunk = await upload_file.read(chunk_size)
        content_str = chunk.decode("utf-8")
        csv_file = io.StringIO(content_str)
        reader = csv.DictReader(csv_file)
        required_columns: list[str] = ["scac", "kn_port_code", "carrier_port_code"]
        if reader.fieldnames is required_columns:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="File is missing one or more required columns.")
        try:
            validated = PORT_CODE_ADAPTER.validate_python(reader)
            await db.bulk_set(PORT_CODE_ADAPTER.dump_python(validated))
            return JSONResponse(status_code=status.HTTP_200_OK, content='OK')
        except ValidationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Validation error:{e.errors()}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"File upload and validation failed: {str(e)}")


@router.get("/read", summary="Read port code mapping information", response_model=List[PortCodeMapping])
async def read_port_code_mapping(
    scac: CarrierCode | None = Query(default=None, description='Search for port code by carrier code'),
    kn_port_code: str | None = Query(alias='knPortCode', default=None, max_length=5, pattern=r"[A-Z]{2}[A-Z0-9]{3}",
                                     example='HKHKG', description='Search by either port or point of origin')):
    try:
        read_result = await db.read_port_mapping_code(scac=scac, kn_port_code=kn_port_code)
        validated = PORT_CODE_ADAPTER.validate_python(read_result) if read_result else ...
        final_result = PORT_CODE_ADAPTER.dump_python(validated) if read_result else 'No result match the request'
        return JSONResponse(status_code=status.HTTP_200_OK, content=final_result)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Validation error:{e.errors()}")


@router.put("/update", summary="Update port code mapping information")
async def refresh_port_code_mapping(query_params: Annotated[PortCodeMapping, Query()]):
    """
    Basically this will ONLY clear all the cache we loaded into API hub before and update again with the latest port code mapping
    so if you delete certain port code mapping using delete API, you also have to refresh the port code mapping with this API.
    """
    try:
        updated_result = await db.update_carrier_port_code(scac=query_params.scac,
                                                           kn_port_code=query_params.kn_port_code,
                                                           new_carrier_port_code=query_params.carrier_port_code)
        final_result = jsonable_encoder(updated_result)
        return JSONResponse(status_code=status.HTTP_200_OK, content=final_result)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Refresh error:{e}")


@router.delete("/delete", summary="Delete port code mapping information")
async def delete_port_code_mapping(
    scac: CarrierCode | None = Query(default=None, description='Search for port code by carrier code'),
    kn_port_code: str | None = Query(alias='knPortCode', default=None, max_length=5, pattern=r"[A-Z]{2}[A-Z0-9]{3}",
                                     example='HKHKG', description='Search by either port or point of origin')):
    """
    You can choose to delete either all the port mapping  or specific port mapping based on scac or/and kn port code
    """
    try:
        await db.delete_port_mapping_code(scac=scac, kn_port_code=kn_port_code)
        return JSONResponse(status_code=status.HTTP_200_OK, content='Deleted all entries')
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Validation error:{e.errors()}")
