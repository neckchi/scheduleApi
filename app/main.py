import uvicorn
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

from app.api.handler.p2p_schedule import schedules_router
from app.api.handler.port_mapping import port_map
from app.api.schemas.schema_response import HealthCheck
from app.internal.http.http_client_manager import startup_event, shutdown_event
from app.internal.http.middleware import RequestContextLogMiddleware
from app.internal.setting import load_yaml

app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(RequestContextLogMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=['GET'],
	allow_headers=["*"],
)

app.include_router(schedules_router.router)
app.include_router(port_map.router)
app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)


@app.get("/health", tags=["healthcheck"], summary="Perform a Health Check",
         response_description="Return HTTP Status Code 200 (OK)", status_code=status.HTTP_200_OK,
         response_model=HealthCheck)
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
	uvicorn.run("app.main:app", host="0.0.0.0", port=8000,
	            timeout_keep_alive=load_yaml()['data']['connectionPoolSetting']['keepAliveExpiry'])

# uvicorn.run("main:app", port=8000, workers=4)
