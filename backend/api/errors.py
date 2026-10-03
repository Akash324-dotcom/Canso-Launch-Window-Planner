"""The exception vocabulary of the /v1 surface, and the HTTP model of spec IV.7.

Spec IV.7 rule 1: any semantically valid request that the physics answers
returns HTTP 200 with a body, including "unreachable", "no windows" and
"constraint fired". Spec IV.7 rule 3: constraint outcomes live in the body, never
as HTTP errors. So none of the classes below is ever raised for a physics
outcome; they exist only for the four conditions of rule 2.

Every class carries the fields its handler needs, so a handler is a pure mapping
from an exception to a status code, a JSON body and any headers, and never has
to guess.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VIOLATION = "request_schema_violation"
UNKNOWN_RESOURCE = "unknown_resource"
RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
UPSTREAM_UNAVAILABLE = "upstream_unavailable"
INTERNAL_ERROR = "internal_error"


class ApiError(Exception):
    """Base class for the exceptions that map to a 4xx or 5xx body."""

    status_code = 500
    error = INTERNAL_ERROR

    def __init__(self, detail: str, **context: Any) -> None:
        super().__init__(detail)
        self.detail = detail
        self.context = context

    def body(self) -> dict[str, Any]:
        """The JSON body for this error: always a ``detail`` string, plus context."""
        return {"detail": self.detail, "error": self.error, **self.context}

    def headers(self) -> dict[str, str]:
        return {}


class ContractViolation(ApiError):
    """The request body does not satisfy the frozen request schema (spec IV.7 rule 2)."""

    status_code = 422
    error = SCHEMA_VIOLATION

    def __init__(self, detail: str, schema_name: str | None = None, violations: list[str] | None = None) -> None:
        super().__init__(detail, schema_name=schema_name, violations=violations or [])


class UnknownResourceError(ApiError):
    """An orbit id, site id or run id in the request is not one the service knows."""

    status_code = 404
    error = UNKNOWN_RESOURCE

    def __init__(
        self, resource_kind: str, resource_id: str, detail: str | None = None
    ) -> None:
        super().__init__(
            detail or f"unknown {resource_kind} id {resource_id!r}",
            resource_kind=resource_kind,
            resource_id=resource_id,
        )
        self.resource_kind = resource_kind
        self.resource_id = resource_id


class RateLimitExceeded(ApiError):
    """The per-IP request budget for this route is spent (spec IV.8)."""

    status_code = 429
    error = RATE_LIMIT_EXCEEDED

    def __init__(self, detail: str, retry_after_s: int) -> None:
        super().__init__(detail, retry_after_s=int(retry_after_s))
        self.retry_after_s = int(retry_after_s)

    def headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_s)}


class UpstreamUnavailable(ApiError):
    """A live layer is unreachable, so the offline fixture path answers instead.

    Spec V.5: the demo must survive a dead upstream. The body therefore always
    states which precomputed path is active, so that no client can mistake a
    fixture answer for a live one.
    """

    status_code = 503
    error = UPSTREAM_UNAVAILABLE

    def __init__(
        self,
        detail: str,
        retry_after_s: int,
        fixture_path: str | None = None,
        layer: str = "upstream",
    ) -> None:
        super().__init__(
            detail,
            layer=layer,
            retry_after_s=int(retry_after_s),
            fixture_path_active=True,
            offline_fixture_path=fixture_path,
        )
        self.retry_after_s = int(retry_after_s)
        self.fixture_path = fixture_path
        self.layer = layer

    def headers(self) -> dict[str, str]:
        return {"Retry-After": str(self.retry_after_s)}