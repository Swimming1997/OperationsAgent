from fastapi import FastAPI

from intelligence_engine.api.account_login_routes import router as account_login_router
from intelligence_engine.api.auth_routes import router as auth_router
from intelligence_engine.api.media_routes import router as media_router
from intelligence_engine.api.operations_routes import router as operations_router
from intelligence_engine.api.product_routes import router as product_router
from intelligence_engine.api.routes import router
from intelligence_engine.config import get_settings
from intelligence_engine.db.init_db import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(router)
    app.include_router(auth_router)
    app.include_router(media_router)
    app.include_router(product_router)
    app.include_router(operations_router)
    app.include_router(account_login_router)

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    return app


app = create_app()
