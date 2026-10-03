"""The /v1 routers. Task A2 wires them under one versioned prefix."""

from backend.api.routes.windows import router as windows_router

ROUTERS = (windows_router,)

__all__ = ["ROUTERS", "windows_router"]