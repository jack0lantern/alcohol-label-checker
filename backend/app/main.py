from fastapi import FastAPI

from app.api.routes_verify import router as verify_router
from app.api.routes_ws import router as ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Alcohol Label Checker API")
    app.include_router(verify_router)
    app.include_router(ws_router)
    return app


app = create_app()
