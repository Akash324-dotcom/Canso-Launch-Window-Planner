"""The /v1 routers. Task A2 wires them under one versioned prefix."""

from backend.api.routes.citation import router as citation_router
from backend.api.routes.decision import router as decision_router
from backend.api.routes.ephemeris import router as ephemeris_router
from backend.api.routes.site import router as site_router
from backend.api.routes.weather import router as weather_router
from backend.api.routes.windows import router as windows_router

ROUTERS = (
    windows_router,
    weather_router,
    ephemeris_router,
    site_router,
    citation_router,
    decision_router,
)

__all__ = [
    "ROUTERS",
    "citation_router",
    "decision_router",
    "ephemeris_router",
    "site_router",
    "weather_router",
    "windows_router",
]