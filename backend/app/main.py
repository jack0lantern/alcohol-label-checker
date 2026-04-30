import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes_health import router as health_router
from app.api.routes_verify import router as verify_router
from app.api.routes_ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Alcohol Label Checker API")
    app.include_router(health_router)
    app.include_router(verify_router)
    app.include_router(ws_router)

    dist = os.environ.get("FRONTEND_DIST")
    if dist:
        static_path = Path(dist).resolve()
        if static_path.is_dir():
            app.mount("/", StaticFiles(directory=str(static_path), html=True), name="frontend")

    return app


app = create_app()
