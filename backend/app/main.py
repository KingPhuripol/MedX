"""App factory. Run: ``uvicorn --factory app.main:create_app --host 127.0.0.1``."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request

from . import auth, public_demo, voice
from .care import router as care_router
from .config import Settings
from .db import create_schema, make_engine
from .demo import router as demo_router
from .gateway import build_provider
from .gateway import router as gateway_router
from .pharma import router as pharma_router
from .pharma.db import create_pharma_schema
from .triage import casegraph_run
from .triage import router as triage_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = make_engine(settings.database_url)
    if settings.public_demo:  # d1: schema + synthetic users on every cold start (idempotent)
        public_demo.bootstrap(engine)
    else:
        create_schema(engine)
        voice.create_voice_schema(engine)
        create_pharma_schema(engine)

    app = FastAPI(title="Clinical Front Door (research prototype)", version="0.1.0")
    app.state.settings = settings
    app.state.engine = engine
    app.state.provider = build_provider(settings.gateway_provider, settings)
    app.state.casegraph = casegraph_run.stores_for(settings)  # i2: the Case Graph behind triage assessments

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
    if settings.public_demo:
        app.include_router(public_demo.router)
    app.include_router(gateway_router.router)
    app.include_router(voice.router)
    app.include_router(triage_router.router)
    app.include_router(care_router.router)
    app.include_router(pharma_router.router)
    app.include_router(demo_router.router)
    return app
