"""The FastAPI application and the error model of spec IV.7, task A2 of issue #4.

Every /v1 router is mounted under one versioned prefix, and the OpenAPI document is
served from inside that prefix at ``/v1/openapi.json`` as spec IV requires.

The handlers are the whole point of this module. Spec IV.7 reserves 4xx for four
conditions only, so each handler here is a thin mapping from one exception to one
status code, one JSON body and, where the specification demands it, one header:

* a request the engine cannot interpret is 422, never 500, and the body names the
  frozen schema the request violated;
* an orbit, site or run id the service does not know is 404 with a JSON detail,
  because it is a genuine resource miss and not a domain outcome;
* a spent request budget is 429 with Retry-After;
* a dead upstream is 503 with Retry-After and a body that states which offline
  fixture path is answering, so that no client can mistake a precomputed answer for
  a live one (spec V.5).

Physics outcomes are not here, and must never be added here: unreachable, an empty
window list and a fired constraint are answers and belong in the 200 body.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.config import Settings, get_settings
from backend.api.errors import INTERNAL_ERROR, ApiError, ContractViolation, UnknownResourceError
from backend.api.routes import ROUTERS
from backend.api.schemas import contract_schema_dir

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_TITLE = "Launch window decision engine"
OPENAPI_DESCRIPTION = (
    "Versioned REST surface of the Canso launch window decision engine. Spec Part IV "
    "is the contract: the schemas served here are the frozen files under "
    "tests/contract/schemas, not a parallel copy."
)
API_DESCRIPTION = (
    "Physics answers are HTTP 200, including an unreachable target, an empty window "
    "list and a fired constraint. HTTP 4xx and 5xx are reserved for malformed "
    "requests and unavailable layers. See spec IV.7."
)


def error_response(error: ApiError) -> JSONResponse:
    """Render one domain exception as its status code, body and headers."""
    return JSONResponse(status_code=error.status_code, content=error.body(), headers=error.headers())


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the spec IV.7 handlers to an application.

    Exposed as a function so that the handlers can be exercised directly, without a
    route that exists only to raise, while still being the handlers the service runs.
    """

    @app.exception_handler(RequestValidationError)
    async def on_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """A body FastAPI itself could not parse is a malformed request, so 422."""
        violations = [
            f"/{'/'.join(str(part) for part in error.get('loc', ())[1:])}: {error.get('msg', '')}"
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "the request body could not be read as a JSON object",
                "error": "request_schema_violation",
                "schema_name": "windows_request",
                "violations": violations,
            },
        )

    @app.exception_handler(ContractViolation)
    async def on_contract_violation(request: Request, exc: ContractViolation) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(UnknownResourceError)
    async def on_unknown_resource(request: Request, exc: UnknownResourceError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(ApiError)
    async def on_api_error(request: Request, exc: ApiError) -> JSONResponse:
        """429, 503 and anything else the vocabulary defines, mapped by its own class."""
        return error_response(exc)

    @app.exception_handler(Exception)
    async def on_unexpected_failure(request: Request, exc: Exception) -> JSONResponse:
        """A last resort so that a bug is a readable JSON body and not a bare crash.

        This handler is deliberately not reachable from any documented request: a
        malformed body must never land here, which the A2 tests assert directly.
        """
        return JSONResponse(
            status_code=500,
            content={
                "detail": "the service failed to answer this request; see the service log",
                "error": INTERNAL_ERROR,
                "exception": type(exc).__name__,
            },
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the service. Passing settings is how a test points it at other data."""
    resolved = settings or get_settings()
    prefix = resolved.api_prefix
    application = FastAPI(
        title=OPENAPI_TITLE,
        description=OPENAPI_DESCRIPTION,
        version="0.1.0",
        openapi_url=f"{prefix}/openapi.json",
        docs_url=f"{prefix}/docs",
        redoc_url=None,
    )
    application.dependency_overrides[get_settings] = lambda: resolved
    for router in ROUTERS:
        application.include_router(router, prefix=prefix)
    register_exception_handlers(application)

    @application.get(f"{prefix}/health", tags=["service"])
    def health() -> dict[str, Any]:
        """Liveness plus the provenance of the configuration in force."""
        return {
            "status": "ok",
            "api_prefix": prefix,
            "contract_schema_dir": str(contract_schema_dir()),
            "default_site": resolved.default_site,
            "offline_fixture_paths": resolved.fixture_paths,
        }

    return application


app = create_app()