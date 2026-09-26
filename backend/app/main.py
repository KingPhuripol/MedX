"""App factory. Run: ``uvicorn --factory app.main:create_app --host 127.0.0.1``."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request

from . import auth
from .config import Settings
from .db import create_schema, make_engine
from .gateway import build_provider
from .gateway import router as gateway_router
from .triage import router as triage_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    create_schema(engine)

    app = FastAPI(title="Clinical Front Door (research prototype)", version="0.1.0")
    app.state.settings = settings
    app.state.engine = engine
    app.state.provider = build_provider(settings.gateway_provider, settings)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "default_provider": settings.gateway_provider, "research_prototype": True}

    app.include_router(auth.router)
    app.include_router(gateway_router.router)
    app.include_router(triage_router.router)
    return app
