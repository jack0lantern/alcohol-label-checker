import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes_health import router as health_router
from app.api.routes_verify import router as verify_router
from app.api.routes_ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Alcohol Label Checker API")

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if allowed_origins != "":
        origins = ["*"] if allowed_origins == "*" else [o.strip() for o in allowed_origins.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
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
