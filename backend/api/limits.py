"""Per-client request budgets, spec IV.8, task A7 of issue #4.

Spec IV.8 allows no authentication on read endpoints, because researcher reuse is
the point, so the only protection is a budget per client address: 60 requests per
minute on ``POST /v1/windows`` and 120 per minute on the reads. A breach is 429
with ``Retry-After``, which spec IV.7 rule 2 names.

Every number arrives through ``backend/api/data/service.json``; nothing here is a
literal. ``enabled`` switches the limiter off, which is what keeps one test's budget
from spending another's, and which a deployment behind its own proxy would use.

The window is sliding rather than fixed, because a fixed window lets a client spend
a whole budget at the end of one minute and another at the start of the next. The
limiter hangs off the application object, so two applications in one process do not
share a budget.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Any, Callable

from backend.api.errors import RateLimitExceeded

POST_WINDOWS_BUCKET = "post_windows"
READ_BUCKET = "read"
BUCKETS = (POST_WINDOWS_BUCKET, READ_BUCKET)


def client_key(request: Any) -> str:
    """The client a budget belongs to.

    The socket address is the primary key. ``X-Forwarded-For`` is honoured only
    because the service is expected to run behind a reverse proxy in deployment,
    where every request would otherwise arrive from the proxy and share one budget.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client is not None else "unknown"


class RateLimiter:
    """A sliding-window request counter per client and per bucket."""

    def __init__(
        self,
        config: dict[str, Any],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.enabled = bool(config["enabled"])
        self.window_s = float(config["window_s"])
        self.retry_after_s = int(config["retry_after_s"])
        self._limits = {
            POST_WINDOWS_BUCKET: int(config["post_windows_per_window"]),
            READ_BUCKET: int(config["reads_per_window"]),
        }
        self._clock = clock
        self._requests: dict[tuple[str, str], list[float]] = defaultdict(list)
        self.rejections = 0

    def limit_for(self, bucket: str) -> int:
        try:
            return self._limits[bucket]
        except KeyError:
            raise ValueError(
                f"no request budget is configured for {bucket!r}; known: {sorted(self._limits)}"
            ) from None

    def check(self, bucket: str, key: str) -> None:
        """Record one request against a budget, or raise the 429 of spec IV.7."""
        if not self.enabled:
            return
        limit = self.limit_for(bucket)
        now = self._clock()
        window = self._requests[(bucket, key)]
        self._requests[(bucket, key)] = kept = [stamp for stamp in window if now - stamp < self.window_s]
        if len(kept) >= limit:
            self.rejections += 1
            retry_after = max(1, math.ceil(self.window_s - (now - kept[0])))
            raise RateLimitExceeded(
                f"the per-client budget of {limit} requests per {self.window_s:g} s on "
                f"{bucket} is spent; retry after {retry_after} s",
                retry_after_s=retry_after,
            )
        kept.append(now)

    def spent(self, bucket: str, key: str) -> int:
        """How many requests the budget currently holds for one client."""
        return len(self._requests.get((bucket, key), ()))

    def reset(self) -> None:
        self._requests.clear()
        self.rejections = 0

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "window_s": self.window_s,
            "limits": dict(self._limits),
            "rejections": self.rejections,
        }