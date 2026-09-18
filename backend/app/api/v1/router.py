"""Aggregates the v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    alerts,
    analytics,
    auth,
    observations,
    research,
    sensors,
    species,
    users,
    verifications,
    zones,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(species.router)
api_router.include_router(observations.router)
api_router.include_router(ai.router)
api_router.include_router(zones.router)
api_router.include_router(analytics.router)
api_router.include_router(verifications.router)
api_router.include_router(alerts.router)
api_router.include_router(sensors.router)
api_router.include_router(research.router)
