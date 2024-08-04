from fastapi import FastAPI,status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from app.routers import schedules
from app.schemas.schema_response import HealthCheck
from app.routers.router_config import startup_event,shutdown_event
import uvicorn



app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=['GET'],
    allow_headers=["*"],
)
app.include_router(schedules.router)
app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)


@app.get("/health",tags=["healthcheck"],summary="Perform a Health Check",response_description="Return HTTP Status Code 200 (OK)",status_code=status.HTTP_200_OK,response_model=HealthCheck)
async def get_health() -> HealthCheck:
    return HealthCheck(status=f"OK")
@app.get("/docs", include_in_schema=False)
def overridden_swagger():
    return get_swagger_ui_html(openapi_url="/openapi.json", title="P2P Schedule API Hub",
                               swagger_favicon_url="https://ca.kuehne-nagel.com/o/kn-lgo-theme/images/favicons/favicon.ico")
@app.get("/redoc", include_in_schema=False)
def overridden_redoc():
    return get_redoc_html(openapi_url="/openapi.json", title="P2P Schedule API Hub",
                          redoc_favicon_url="https://ca.kuehne-nagel.com/o/kn-lgo-theme/images/favicons/favicon.ico")
def custom_openapi():
    """
    By using this way,this application won't have to generate the schema every time a user opens our API docs.
    """
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="API Point To Point Schedule Hub",
        version="1.0.1",
        description="Get Single Source Of Truth In Real Time",
        contact={'pic': 'neck.chi@kuehne-nagel.com'},
        routes=app.routes,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": "https://ca.kuehne-nagel.com/o/kn-lgo-theme/images/kuehne-nagel-logo-blue.png"
    }
    app.openapi_schema = openapi_schema
    return app.openapi_schema



app.openapi = custom_openapi

if __name__ == "__main__":
    uvicorn.run("app.main:app",host="0.0.0.0", port=8000,timeout_keep_alive=25)

    # uvicorn.run("main:app", port=8000, workers=4)
