"""Cache and rate-limit plumbing for the /v1 routes, spec IV.8, task A7.

Two small helpers keep every route the same shape:

* ``cached_response`` wraps a read endpoint, keying on the method, the path and the
  query, so an identical request within the lifetime is replayed rather than
  recomputed;
* ``rate_limited`` is a route dependency that spends a request from the per-client
  budget before the endpoint runs, so a breach is a 429 with ``Retry-After`` rather
  than an exception raised from inside the handler.

Both live on the application object, not in module globals, so two applications in
one process share neither a cache nor a budget. ``/v1/openapi.json`` and
``/v1/health`` are not wrapped and not charged: a client reading the contract or
polling for liveness is not using the research budget.
"""

from __future__ import annotations

import copy
from typing import Any, Callable

from fastapi import Request

from backend.api.cache import CacheRegistry, cache_key
from backend.api.limits import RateLimiter, client_key

READS_CACHE = "reads"


def cache_registry(request: Request) -> CacheRegistry | None:
    """The application's cache registry, when the application has one."""
    return getattr(request.app.state, "cache_registry", None)


def read_cache_key(request: Request) -> str:
    """The spec IV.8 key for a read: the method, the path and the query."""
    return cache_key(
        READS_CACHE,
        {
            "method": request.method,
            "path": request.url.path,
            "query": sorted(request.query_params.multi_items()),
        },
    )


def cached_response(request: Request, build: Callable[[], Any]) -> Any:
    """Serve a read from the cache when it is within its lifetime, else build it."""
    registry = cache_registry(request)
    if registry is None:
        return build()
    cache = registry[READS_CACHE]
    key = read_cache_key(request)
    entry = cache.get(key)
    if entry is not None:
        return copy.deepcopy(entry.value)
    value = build()
    cache.put(key, value)
    return value


def rate_limited(bucket: str) -> Callable[[Request], None]:
    """A route dependency that charges one request from the per-client budget."""

    def dependency(request: Request) -> None:
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is not None:
            limiter.check(bucket, client_key(request))

    return dependency