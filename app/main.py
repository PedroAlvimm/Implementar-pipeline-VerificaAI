from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dependencies import AppContainer, build_default_container
from app.api.routes import build_router


def create_app(container: AppContainer | None = None) -> FastAPI:
    current = container or build_default_container()
    app = FastAPI(title="VerificaAI", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )
    app.include_router(build_router(current))
    return app

