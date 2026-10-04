"""The WEATHER seam of ``docs/00_INTEGRATION_CONTRACT.md``, task A4 of issue #4.

Seam 1 freezes two plain functions:

    probability(date_iso, site, criteria_version=None) -> dict   # spec IV.3 body
    hindcast(period_start, period_end, lead_max=10)     -> dict   # spec IV.4 body

This module is the only place that decides where an answer comes from. The order
is fixed by spec IV.7 rule 2 and spec V.5:

1. a cached answer, while it is within its configured lifetime, echoed with the
   ``forecast_issue_time`` stored beside it so that a cached answer is never
   presented as a fresh fetch;
2. the live WEATHER module, when it exists, called with the frozen keyword names;
3. the recorded offline document under ``backend/fixtures``, which is the demo
   floor of spec V.5;
4. a genuine outage, 503 with Retry-After and the offline path named, when neither
   the layer nor the record can answer the request.

**The chosen behaviour when the weather layer raises is that windows still
return.** Spec IV.7 rule 1 makes HTTP 200 the answer for every well formed
request, whatever the weather says, so a dead weather layer must not fail the
window route. A cached answer is served when there is one. When there is not, the
window rows carry ``forecast_issue_time: null``, ``horizon_label: CLIMATOLOGY``,
``p_success_components.weather: 1.0`` and ``p_success`` equal to the product of the
two deterministic pre-screens. That is the neutral set the frozen
``windows_response.json`` admits: it types ``p_success``,
``p_success_components.weather`` and ``horizon_label`` as non-nullable, so null is
available for one of the four weather fields only, and CLIMATOLOGY is the honest
label for a probability no forecast produced. ``backend/fixtures/weather.json`` is
then absent from ``source_files``, because that run did not read it.

The weather GET endpoints have no such fallback, because a body of nothing but
neutral values would answer a question nobody asked. They degrade to the recorded
document, and only when that is unavailable too do they return 503.
"""

from __future__ import annotations

import datetime as dt
import importlib
import json
from typing import Any

from backend.api.cache import CacheRegistry, cache_key
from backend.api.config import Settings
from backend.api.errors import UpstreamUnavailable
from backend.api.stubs import load_weather_document

WEATHER_CACHE = "weather"
WINDOW_CACHE_NAMESPACE = "weather-windows"

# The enumerated ``constraint_fired`` value of spec IV.1 for a criteria version no table exists for.
CRITERIA_VERSION_MISSING = "criteria_version_missing"

NEUTRAL_HORIZON_LABEL = "CLIMATOLOGY"
NEUTRAL_WEATHER_COMPONENT = 1.0


def _weather_module() -> Any | None:
    """The weather layer as the import system resolves it, or None when it is absent.

    ``importlib.import_module`` reads ``sys.modules``, so the module a test installs or
    removes there is the one the service sees. ``from backend import weather`` would
    return the attribute of the ``backend`` package once the real module has been
    imported, whatever ``sys.modules`` holds.
    """
    try:
        return importlib.import_module("backend.weather")
    except ImportError:
        return None


def live_probability() -> Any | None:
    """``backend.weather.probability`` once WEATHER lands, else None."""
    weather = _weather_module()
    return getattr(weather, "probability", None)


def live_hindcast() -> Any | None:
    """``backend.weather.hindcast`` once WEATHER lands, else None."""
    weather = _weather_module()
    return getattr(weather, "hindcast", None)


def parse_iso_date(value: str, field: str) -> dt.date:
    """Parse a query date, reporting a malformed one as a 422 rather than a 500."""
    from backend.api.errors import ContractViolation

    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ContractViolation(
            f"{field} must be an ISO-8601 calendar date of the form YYYY-MM-DD",
            schema_name="weather_probability_response",
            violations=[f"/{field}: {value!r} is not a YYYY-MM-DD date"],
        ) from None


# --------------------------------------------------------------------- the keys


def weather_cache_key(date_iso: str, site: str, criteria_version: str | None) -> str:
    """The spec IV.8 weather key: the request the answer belongs to.

    Spec IV.8 keys the weather cache by date, site and source and stores
    ``forecast_issue_time`` with the entry. The criteria version joins the key
    because a different criteria table is a different answer for the same day.
    """
    return cache_key(
        WEATHER_CACHE, {"date": date_iso, "site": site, "criteria_version": criteria_version}
    )


def window_weather_cache_key(effective_request: dict[str, Any]) -> str:
    """The weather key used while composing the window rows of one request."""
    return cache_key(
        WINDOW_CACHE_NAMESPACE,
        {
            "site": effective_request.get("site"),
            "criteria_version": effective_request.get("criteria_version"),
            "date_range": effective_request.get("date_range"),
        },
    )


def _lookup(registry: CacheRegistry | None, key: str) -> dict[str, Any] | None:
    if registry is None:
        return None
    entry = registry[WEATHER_CACHE].get(key)
    return None if entry is None else dict(entry.value)


def _store(
    registry: CacheRegistry | None, key: str, document: dict[str, Any]
) -> dict[str, Any]:
    if registry is not None:
        registry[WEATHER_CACHE].put(
            key, document, forecast_issue_time=document.get("forecast_issue_time")
        )
    return document


# ----------------------------------------------------- GET /v1/weather/probability


def probability_document(
    settings: Settings,
    registry: CacheRegistry | None,
    date_iso: str,
    site: str,
    criteria_version: str | None,
) -> dict[str, Any]:
    """The spec IV.3 body for one date and site.

    An unknown site is a 404, because spec IV.7 rule 2 reserves it for an unknown
    site id. A dead layer degrades to the recorded snapshot, which is the offline
    fallback of spec V.5. A date the record does not cover is a 503 naming the
    record, because a launch probability for a day nothing recorded is not an
    answer the service may invent.
    """
    parse_iso_date(date_iso, "date")
    settings.site_document(site)
    key = weather_cache_key(date_iso, site, criteria_version)

    cached = _lookup(registry, key)
    if cached is not None:
        return cached

    layer = live_probability()
    if layer is not None:
        try:
            document = dict(layer(date_iso=date_iso, site=site, criteria_version=criteria_version))
        except Exception:
            document = _recorded_probability(settings, date_iso)
        else:
            return _store(registry, key, document)

    else:
        document = _recorded_probability(settings, date_iso)
    return _store(registry, key, document)


def _recorded_probability(settings: Settings, date_iso: str) -> dict[str, Any]:
    """The offline snapshot, when it records the day that was asked for."""
    recorded = load_weather_document(settings)
    if str(recorded["date"]) != date_iso:
        raise UpstreamUnavailable(
            f"the weather layer is unavailable and the recorded offline forecast at "
            f"{settings.relative(settings.fixture_path('weather'))} covers "
            f"{recorded['date']} only, not {date_iso}",
            retry_after_s=settings.retry_after_s["upstream_unavailable"],
            fixture_path=settings.relative(settings.fixture_path("weather")),
            layer="weather",
        )
    return recorded


# --------------------------------------------------------- GET /v1/validation/skill


def skill_document(
    settings: Settings,
    registry: CacheRegistry | None,
    period_start: str,
    period_end: str,
    lead_max: int,
) -> dict[str, Any]:
    """The spec IV.4 body for one verification period, from the seam or the record.

    The requested period is echoed, and the series is truncated to ``lead_max``
    because that is the only thing the parameter can honestly do to a recorded
    series. ``skill_horizon_measured_days`` is left as recorded: it describes the
    verification, not the filter applied to it.
    """
    start = parse_iso_date(period_start, "period_start")
    end = parse_iso_date(period_end, "period_end")
    if end < start:
        from backend.api.errors import ContractViolation

        raise ContractViolation(
            "period_end precedes period_start, so the requested verification window is empty",
            schema_name="skill_response",
            violations=[f"/period: {period_start} is later than {period_end}"],
        )
    if lead_max < 0:
        from backend.api.errors import ContractViolation

        raise ContractViolation(
            "lead_max is a number of days and cannot be negative",
            schema_name="skill_response",
            violations=[f"/lead_max: {lead_max} is negative"],
        )

    layer = live_hindcast()
    if layer is not None:
        try:
            # The layer is asked for its full lead range and the series is cut below,
            # so that lead_max does to a live answer exactly what it does to the record.
            document = dict(layer(period_start=period_start, period_end=period_end))
        except Exception:
            document = _skill_record(settings, period_start, period_end)
    else:
        document = _skill_record(settings, period_start, period_end)

    document["period"] = {"start": period_start, "end": period_end}
    document["skill_series"] = [
        row for row in document["skill_series"] if float(row["lead_time_days"]) <= float(lead_max)
    ]
    from backend.api.provenance import constants_block_for

    document["constants_block"] = constants_block_for(
        settings, date_start=period_start, request_payload={"endpoint": "validation/skill"}
    )
    return document


def _skill_record(settings: Settings, period_start: str, period_end: str) -> dict[str, Any]:
    from backend.api.errors import UpstreamUnavailable

    path = settings.fixture_path("skill")
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        raise UpstreamUnavailable(
            f"the weather layer is unreachable and the recorded hindcast at "
            f"{settings.relative(path)} could not be read: {failure}",
            retry_after_s=settings.retry_after_s["upstream_unavailable"],
            fixture_path=settings.relative(path),
            layer="weather",
        ) from failure
    window = recorded["period"]
    if [str(window["start"]), str(window["end"])] != [period_start, period_end]:
        raise UpstreamUnavailable(
            f"the weather layer is unavailable and the recorded hindcast at "
            f"{settings.relative(path)} covers {window['start']} to {window['end']} only, "
            f"not {period_start} to {period_end}",
            retry_after_s=settings.retry_after_s["upstream_unavailable"],
            fixture_path=settings.relative(path),
            layer="weather",
        )
    return recorded


# ------------------------------------------------ composition on the window route


def window_weather(
    settings: Settings,
    effective_request: dict[str, Any],
    registry: CacheRegistry | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """The one weather document of a window request, and how it was obtained.

    The origin is one of ``excluded``, ``unavailable``, ``cache``, ``live``,
    ``record`` or ``criteria_version_missing``, and is resolved once per response
    rather than once per row: every row of a response shares one weather answer,
    which is also what makes the provenance block of two identical requests identical.

    ``criteria_version_missing`` is not an outage. The weather layer answered that it
    has no criteria table of the requested version, by raising an error that carries
    ``constraint_fired``. Spec IV.7 rule 3 puts that outcome in the body, so the origin
    is handed back for the route to fire the constraint on the rows.
    """
    if not bool(effective_request.get("include_weather", True)):
        return None, "excluded"

    key = window_weather_cache_key(effective_request)
    cached = _lookup(registry, key)
    if cached is not None:
        return cached, "cache"

    layer = live_probability()
    if layer is not None:
        try:
            document = dict(
                layer(
                    date_iso=str((effective_request.get("date_range") or {}).get("start", "")),
                    site=str(effective_request.get("site") or settings.default_site),
                    criteria_version=effective_request.get("criteria_version"),
                )
            )
        except Exception as failure:
            fired = getattr(failure, "constraint_fired", None)
            if fired == CRITERIA_VERSION_MISSING:
                return None, CRITERIA_VERSION_MISSING
            return None, "unavailable"
        _store(registry, key, document)
        return document, "live"

    document = load_weather_document(settings)
    _store(registry, key, document)
    return document, "record"


def compose_window_row(
    document: dict[str, Any] | None, window: dict[str, Any]
) -> dict[str, Any]:
    """The four weather-derived fields of one window row, spec IV.1.

    With a document, the fields come from it and ``p_success`` is recomposed as the
    product of the three components, so a recomposition is idempotent. Without one,
    the neutral set of the module docstring applies.
    """
    components = dict(window.get("p_success_components", {}))
    deterministic = float(components.get("range", 1.0)) * float(components.get("conjunction", 1.0))
    if document is None:
        return _neutral(components, deterministic)
    weather = float(document["p_launch"])
    components["weather"] = weather
    return {
        "p_success": weather * deterministic,
        "p_success_components": components,
        "horizon_label": str(document["horizon_label"]),
        "forecast_issue_time": document.get("forecast_issue_time"),
    }


def compose_window_weather(
    settings: Settings,
    effective_request: dict[str, Any],
    window: dict[str, Any],
    registry: CacheRegistry | None = None,
) -> tuple[dict[str, Any], str]:
    """Convenience wrapper: the fields of one row plus the origin that produced them."""
    document, origin = window_weather(settings, effective_request, registry)
    return compose_window_row(document, window), origin


def _neutral(components: dict[str, Any], deterministic: float) -> dict[str, Any]:
    components["weather"] = NEUTRAL_WEATHER_COMPONENT
    return {
        "p_success": deterministic,
        "p_success_components": components,
        "horizon_label": NEUTRAL_HORIZON_LABEL,
        "forecast_issue_time": None,
    }