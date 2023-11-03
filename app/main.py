from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from app.routers import schedules
from app.background_tasks import db
from os import path
import uvicorn
import logging.config


# setup loggers
log_file_path = path.join(path.dirname(path.abspath(__file__)), 'logging.conf')
logging.config.fileConfig(log_file_path, disable_existing_loggers=False)

# get root logger
logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None)
app.include_router(schedules.router)


# # 👇 Initalize the MongoDB before starting the application
@app.on_event('startup')
async def startup():
    await db.initialize_database()


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


origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['GET'],
    allow_headers=["*"],
)


app.openapi = custom_openapi

if __name__ == "__main__":

    uvicorn.run("app.main:app",host="0.0.0.0", port=8086, reload=True)

    # uvicorn.run("main:app", port=8000, workers=4)
