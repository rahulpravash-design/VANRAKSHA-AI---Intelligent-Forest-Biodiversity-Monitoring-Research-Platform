"""VANRAKSHA AI — application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000

Interactive API documentation is served at ``/docs`` and the OpenAPI schema at
``/openapi.json``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import dialect_name, engine
from app.schemas.common import HealthResponse

logger = logging.getLogger("vanraksha")

DESCRIPTION = """
An intelligent forest biodiversity monitoring and research platform.

**Workflow:** capture → AI-assisted identification → expert verification →
geotagged storage → analytics → unusual-pattern detection → research.

### Two things this API is careful about

*Identifications from a model are AI-assisted, not taxonomy.* Every prediction
carries a confidence, the ranked alternatives, the model version and an
`UNCERTAIN` outcome when the model should not commit. An observation's species
stays what a human reported until a qualified expert confirms or corrects it.

*Counts are detections, not populations.* The sampling design — opportunistic
field records plus fixed camera and acoustic nodes with uneven effort — supports
detection and occurrence analysis, not abundance estimation. Response models say
so where it matters, and diversity indices report when two windows are not
comparable.

Coordinates of threatened and poaching-sensitive taxa are generalised for
callers without precise-location rights; affected records are marked
`location_generalised`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    configure_logging()
    for problem in settings.warn_insecure():
        logger.warning("CONFIGURATION: %s", problem)
    logger.info(
        "%s %s starting (env=%s, database=%s)",
        settings.app_name,
        settings.app_version,
        settings.vanraksha_env,
        dialect_name(),
    )
    if settings.storage_backend.lower() == "local":
        settings.storage_root.mkdir(parents=True, exist_ok=True)
    yield
    engine.dispose()
    logger.info("%s stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "VANRAKSHA AI"},
    license_info={"name": "MIT"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Local media is served by the API for development convenience. In production
# STORAGE_BACKEND=s3 puts media behind object storage / a CDN instead.
if settings.storage_backend.lower() == "local":
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(settings.storage_root)), name="media")


@app.get("/", tags=["meta"], summary="Service banner")
def root() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
    }


@app.get("/health", tags=["meta"], response_model=HealthResponse, summary="Health check")
def health() -> HealthResponse:
    """Reports database connectivity and which AI backends are active."""
    from sqlalchemy import text

    from app.db.session import SessionLocal
    from app.services.ai_client import AIEngine

    database_status = "ok"
    ai_status = "unknown"
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        try:
            info = AIEngine(session).info()
            ai_status = (
                f"{info.mode}: vision={info.vision['backend']}, audio={info.audio['backend']}"
            )
        except Exception as exc:  # pragma: no cover - AI problems must not fail health
            ai_status = f"unavailable ({exc.__class__.__name__})"
    except Exception as exc:
        database_status = f"error: {exc.__class__.__name__}"
    finally:
        session.close()

    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.vanraksha_env,
        database=f"{dialect_name()} ({database_status})",
        ai_engine=ai_status,
    )
