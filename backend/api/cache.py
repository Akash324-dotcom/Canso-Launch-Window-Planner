"""In-memory TTL caches and the cache keys of spec IV.8.

Spec IV.8 fixes three lifetimes and three keys:

* window computations, keyed by a hash of target, site, date range, vehicle,
  corridor, criteria version and RAAN tolerance, cached 24 h;
* weather responses, keyed by the request they answer, cached 30 min, with
  ``forecast_issue_time`` stored in the entry and echoed, so that a cached answer
  is never presented as a fresh fetch;
* read endpoints, cached for a configured lifetime.

Every lifetime arrives through ``backend/api/data/service.json``, never as a literal
here, because requirement 1 and spec IV.8 both put limits in configuration. A
lifetime of zero switches that cache off, which is how a test reaches a code path
that a warm cache would otherwise hide.

The caches live on the application object rather than in a module global, so two
applications in one process do not share entries and a test's warm cache cannot
reach another test.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from backend.api.provenance import sha256_of

CACHE_NAMES = ("windows", "weather", "reads")
CONFIG_KEY_SUFFIX = "_ttl_s"


@dataclass(frozen=True)
class CacheEntry:
    """One stored answer, with the forecast issue time it was produced under."""

    value: Any
    stored_at: float
    forecast_issue_time: str | None = None


def cache_key(namespace: str, payload: Any) -> str:
    """A stable cache key: the namespace plus the digest of the request payload."""
    return f"{namespace}:{sha256_of(payload)}"


class TtlCache:
    """A keyed store whose entries expire after a configured lifetime."""

    def __init__(
        self,
        name: str,
        ttl_s: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.ttl_s = float(ttl_s)
        self._clock = clock
        self._entries: dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        """A lifetime of zero means the cache is switched off."""
        return self.ttl_s > 0.0

    def get(self, key: str) -> CacheEntry | None:
        if not self.enabled:
            self.misses += 1
            return None
        entry = self._entries.get(key)
        if entry is None or self._clock() - entry.stored_at >= self.ttl_s:
            self._entries.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return entry

    def put(self, key: str, value: Any, *, forecast_issue_time: str | None = None) -> None:
        if not self.enabled:
            return
        self._entries[key] = CacheEntry(
            value=value, stored_at=self._clock(), forecast_issue_time=forecast_issue_time
        )

    def flush(self) -> int:
        """Drop every entry. The counters are kept, so a test can still read them."""
        dropped = len(self._entries)
        self._entries.clear()
        return dropped

    def entries(self) -> dict[str, CacheEntry]:
        return dict(self._entries)

    def stats(self) -> dict[str, Any]:
        return {"name": self.name, "ttl_s": self.ttl_s, "entries": len(self._entries), "hits": self.hits, "misses": self.misses}

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, key: str) -> bool:
        return key in self._entries


class CacheRegistry:
    """The three caches of spec IV.8, named and built from one configuration."""

    def __init__(self, config: dict[str, Any], clock: Callable[[], float] = time.monotonic) -> None:
        missing = [name for name in CACHE_NAMES if f"{name}{CONFIG_KEY_SUFFIX}" not in config]
        if missing:
            raise ValueError(f"the cache configuration is missing a lifetime for {missing}")
        self._caches = {
            name: TtlCache(name, float(config[f"{name}{CONFIG_KEY_SUFFIX}"]), clock=clock)
            for name in CACHE_NAMES
        }

    def __getitem__(self, name: str) -> TtlCache:
        return self._caches[name]

    def __iter__(self) -> Iterable[TtlCache]:
        return iter(self._caches.values())

    def names(self) -> list[str]:
        return list(self._caches)

    def flush(self) -> dict[str, int]:
        return {name: cache.flush() for name, cache in self._caches.items()}

    def stats(self) -> dict[str, dict[str, Any]]:
        return {name: cache.stats() for name, cache in self._caches.items()}


def cache_registry(config: dict[str, Any]) -> CacheRegistry:
    return CacheRegistry(config)