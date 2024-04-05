from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from app.routers import schedules
from app.background_tasks import db
from app.config import log_queue_listener
import uvicorn
import atexit


queue_lister = log_queue_listener()
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



# #👇 Initalize the MongoDB/Redis and Logging.Queue before starting the application
@app.on_event('startup')
async def startup():
    queue_lister.start()
    await db.initialize_database()

@app.on_event("shutdown")
def shutdown_event():
    atexit.register(queue_lister.stop)

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

    uvicorn.run("app.main:app",host="0.0.0.0", port=8000, workers = 8)

    # uvicorn.run("main:app", port=8000, workers=4)
