"""The public Python client of the Canso launch window engine, spec IV.9, task A8.

Spec IV.9 asks for three lines: an import, a window call and a ``pandas.DataFrame``.
This module is those three lines, and the read methods that mirror the read
endpoints beside them:

    import launchwin

    frame = launchwin.windows(
        target="SSO", site="canso", dates=("2026-10-05", "2026-10-15"))

Three decisions are worth stating before the code, because each of them is a place
where the specification leaves a choice.

**The DataFrame carries the window rows and the response stays whole.** ``windows``
returns one row per window of the spec IV.1 body, and the untouched response remains
available as ``frame.attrs["response"]``. A response is more than a table: it also
carries ``reachable``, ``plane_change_dv_ms``, ``sso_consistency_warning``, the
constants block and the provenance block. Returning only the rows would make the
provenance of a number unreachable from the number itself, which requirement 1
exists to prevent.

**The two nested objects of a row are flattened into columns.** ``p_success_components``
becomes ``p_weather``, ``p_range`` and ``p_conjunction``, and ``screens`` becomes
``screen_hazard``, ``screen_conjunction`` and ``screen_notam``. The prefix on the
screen columns is not decoration: ``p_success_components`` and ``screens`` both hold
a key called ``conjunction``, so the two objects cannot share one column name
without either losing a field or overwriting the other. The mapping is in
``COMPONENT_COLUMNS`` and ``SCREEN_COLUMNS``, and the complete column order is in
``WINDOW_COLUMNS``.

**A domain outcome is not an error.** Spec IV.7 rule 1 makes an unreachable target,
an empty window list and a fired constraint answers, so ``windows`` returns an empty
DataFrame carrying the full response in ``attrs`` and raises nothing for them.
``LaunchwinError`` is raised for the four conditions of spec IV.7 rule 2 only, that
is 422, 404, 429 and 503, and for a request that never completed at all, which is
neither an answer nor a status code the service chose.

This module is self contained on purpose. It imports ``httpx`` and ``pandas`` and
nothing from ``backend``, so an installed copy works from any directory, which is
what the A8 acceptance test about ``pip install -e .`` is about. ``pandas`` is a
hard dependency rather than an optional one, because a DataFrame is the documented
return type of two of the six public functions and an optional import could only
ever fail at the moment a caller asked for an answer.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx
import pandas

__all__ = [
    "BASE_URL_ENV",
    "COMPONENT_COLUMNS",
    "DEFAULT_BASE_URL",
    "DEFAULT_LEAD_MAX_DAYS",
    "DEFAULT_SITE",
    "DEFAULT_STEP_S",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_VEHICLE_PROFILE_ID",
    "POINT_COLUMNS",
    "SCREEN_COLUMNS",
    "WINDOW_COLUMNS",
    "LaunchwinError",
    "citation",
    "ephemeris",
    "resolve_base_url",
    "site",
    "skill",
    "weather",
    "windows",
    "windows_frame",
]

#: Environment variable holding the ``/v1`` base URL, read when no argument is given.
BASE_URL_ENV = "LAUNCHWIN_URL"
#: The base URL used when neither an argument nor the environment names one.
DEFAULT_BASE_URL = "http://localhost:8000/v1"
#: The default site of spec IV.1.
DEFAULT_SITE = "canso"
#: The default vehicle profile of spec IV.1.
DEFAULT_VEHICLE_PROFILE_ID = "cyclone4m"
#: The ``step_s`` default spec IV.2 writes into the query.
DEFAULT_STEP_S = 300
#: The ``lead_max`` default spec IV.4 writes into the query.
DEFAULT_LEAD_MAX_DAYS = 10
#: Seconds before a request the client owns is abandoned.
DEFAULT_TIMEOUT_S = 30.0

#: Response field to column name for the flattened ``p_success_components``.
COMPONENT_COLUMNS = {
    "p_weather": "weather",
    "p_range": "range",
    "p_conjunction": "conjunction",
}

#: Response field to column name for the flattened ``screens``.
SCREEN_COLUMNS = {
    "screen_hazard": "hazard",
    "screen_conjunction": "conjunction",
    "screen_notam": "notam",
}

#: The spec IV.1 window row as columns, with the two nested objects flattened in place.
WINDOW_COLUMNS = (
    "t_liftoff_utc",
    "t_injection_utc",
    "raan_deg",
    "azimuth_deg",
    "azimuth_compass_deg",
    "reached_inclination_deg",
    "window_width_s",
    "window_center_shift_s",
    "liftoff_instant_error_min",
    "p_success",
    "p_weather",
    "p_range",
    "p_conjunction",
    "horizon_label",
    "forecast_issue_time",
    "constraint_fired",
    "screen_hazard",
    "screen_conjunction",
    "screen_notam",
)

#: The spec IV.2 ephemeris point as columns.
POINT_COLUMNS = ("t_utc", "lat_deg", "lon_deg", "alt_km")


class LaunchwinError(RuntimeError):
    """A request that produced no answer, carrying everything the service said.

    ``status_code`` is the HTTP status of the four conditions spec IV.7 rule 2
    reserves, and is ``None`` when the request never completed, in which case
    ``detail`` holds the transport failure rather than a message from the service.
    ``retry_after_s`` is the ``Retry-After`` header when one was sent, which spec IV.7
    and spec IV.8 require on 429 and on 503. ``payload`` is the parsed body, so that a
    caller can read the ``violations`` of a 422 or the ``offline_fixture_path`` of a
    503 without parsing the message.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: Any = None,
        payload: Any = None,
        retry_after_s: str | None = None,
        method: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail
        self.payload = payload
        self.retry_after_s = retry_after_s
        self.method = method
        self.url = url


def resolve_base_url(base_url: str | None = None) -> str:
    """The ``/v1`` base URL in force: the argument, then the environment, then the default.

    Trailing slashes are removed so that a base URL read from a configuration file and
    one copied from a shell end in the same request URL. An environment variable that
    is set to nothing reads as unset, because that is how a shell spells unset; an
    empty argument is refused rather than replaced by the default, because a caller who
    passed one made a mistake worth seeing.
    """
    if base_url is None:
        base_url = os.environ.get(BASE_URL_ENV) or DEFAULT_BASE_URL
    resolved = str(base_url).strip().rstrip("/")
    if not resolved:
        raise ValueError(
            f"the base URL is empty: pass base_url or set {BASE_URL_ENV}"
        )
    return resolved


def windows(
    target: str | Mapping[str, Any],
    dates: Sequence[str] | Mapping[str, str],
    site: str = DEFAULT_SITE,
    vehicle: str = DEFAULT_VEHICLE_PROFILE_ID,
    include_weather: bool = True,
    base_url: str | None = None,
    client: Any | None = None,
) -> "pandas.DataFrame":
    """Launch windows for one target, site, date range and vehicle, spec IV.1.

    ``target`` is either a target class name, one of ``LEO``, ``POLAR``, ``SSO`` or
    ``CUSTOM``, or a complete spec IV.1 target object, which is what a CUSTOM orbit
    with its own altitude and inclination needs. ``dates`` is a ``(start, end)`` pair
    of ISO dates or a mapping with ``start`` and ``end`` keys.

    Returns one row per window, with the columns of ``WINDOW_COLUMNS``, and the whole
    spec IV.1 response in ``frame.attrs["response"]``. An unreachable target and an
    empty window list both return a DataFrame with no rows and that response intact:
    both are answers of spec IV.7 rule 1 and neither raises.
    """
    body = {
        "target": _target_document(target),
        "site": site,
        "date_range": _date_range(dates),
        "vehicle_profile_id": vehicle,
        "include_weather": bool(include_weather),
    }
    response = _request("POST", "windows", base_url=base_url, client=client, body=body)
    return windows_frame(response)


def windows_frame(response: Mapping[str, Any]) -> "pandas.DataFrame":
    """A spec IV.1 response as one row per window, keeping the response whole.

    Exposed because the DataFrame shape is part of the client's contract and is worth
    being able to build from a response that was stored rather than fetched, for
    example the one ``GET /v1/citation`` points at.
    """
    if not isinstance(response, Mapping):
        raise TypeError(
            "a windows response must be the JSON object of spec IV.1, not "
            f"{type(response).__name__}"
        )
    rows = [_window_row(window) for window in response.get("windows") or ()]
    frame = pandas.DataFrame(rows, columns=list(WINDOW_COLUMNS))
    frame.attrs["response"] = dict(response)
    return frame


def weather(
    date: str,
    site: str = DEFAULT_SITE,
    base_url: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """The launch probability for one date and site, spec IV.3, as the document.

    The response is returned as the JSON object rather than as a frame, because a
    probability is one number with its evidence beside it, not a series: the
    components, the horizon label, the forecast issue time and the source are part of
    the answer and the reader needs them.
    """
    return _request(
        "GET",
        "weather/probability",
        base_url=base_url,
        client=client,
        params={"date": str(date), "site": site},
    )


def skill(
    period_start: str,
    period_end: str,
    lead_max: int = DEFAULT_LEAD_MAX_DAYS,
    base_url: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """The hindcast verification series for one period, spec IV.4, as the document."""
    return _request(
        "GET",
        "validation/skill",
        base_url=base_url,
        client=client,
        params={
            "period_start": str(period_start),
            "period_end": str(period_end),
            "lead_max": lead_max,
        },
    )


def site(
    site_id: str | None = None,
    base_url: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """The site geometry and corridor record, spec IV.5, as the document.

    ``site_id`` is omitted from the query when it is ``None``, so that the service
    answers with the site its own configuration names rather than with the one this
    module names.
    """
    params = {"site": site_id} if site_id is not None else None
    return _request("GET", "site", base_url=base_url, client=client, params=params)


def ephemeris(
    orbit_id: str,
    start: str,
    end: str,
    step_s: float = DEFAULT_STEP_S,
    base_url: str | None = None,
    client: Any | None = None,
) -> "pandas.DataFrame":
    """One ECEF ground track, spec IV.2, as one row per point.

    The columns are ``POINT_COLUMNS``, and the whole response, including
    ``ground_track_valid`` and the constants block, is in
    ``frame.attrs["response"]``. ``ground_track_valid`` belongs there rather than in a
    column because it qualifies the whole track: a reader must not be able to sort or
    filter the points into believing they are valid when the service says the
    propagation horizon has been passed.
    """
    response = _request(
        "GET",
        f"orbits/{quote(str(orbit_id), safe='')}/ephemeris",
        base_url=base_url,
        client=client,
        params={"start": str(start), "end": str(end), "step_s": step_s},
    )
    frame = pandas.DataFrame(list(response.get("points") or ()), columns=list(POINT_COLUMNS))
    frame.attrs["response"] = response
    return frame


def citation(
    citation_id: str,
    base_url: str | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """The spec II.10 provenance table of one stored run, spec IV.6, as the document.

    An identifier no run stored raises ``LaunchwinError`` with status 404, because
    that is a genuine resource miss and spec IV.7 rule 2 reserves 404 for exactly it.
    """
    return _request(
        "GET",
        "citation",
        base_url=base_url,
        client=client,
        params={"id": str(citation_id)},
    )


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------


def _request(
    method: str,
    path: str,
    *,
    base_url: str | None = None,
    client: Any | None = None,
    params: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
) -> Any:
    """One request, parsed, with the spec IV.7 error model applied to it.

    ``client`` may be any object with the ``httpx.Client`` interface, which is how a
    test passes a FastAPI ``TestClient`` and therefore exercises the real request
    building against the real application. Without one the module opens an
    ``httpx.Client`` of its own and closes it when the response is in hand, so the
    client never leaves a connection pool behind.
    """
    url = f"{resolve_base_url(base_url)}/{path.lstrip('/')}"
    owns_transport = client is None
    transport = httpx.Client(timeout=DEFAULT_TIMEOUT_S) if owns_transport else client
    try:
        try:
            response = transport.request(method, url, params=params, json=body)
        except httpx.HTTPError as failure:
            raise LaunchwinError(
                f"{method} {url} did not complete: {type(failure).__name__}: {failure}",
                detail=str(failure),
                method=method,
                url=url,
            ) from failure
    finally:
        if owns_transport:
            transport.close()
    if response.status_code >= 400:
        raise _service_error(response, method, url)
    return response.json()


def _service_error(response: Any, method: str, url: str) -> LaunchwinError:
    """Turn a 4xx or 5xx response into a ``LaunchwinError`` that states the reason.

    The detail of the service error model is a JSON ``detail`` field, so that is what
    the message carries. A body without one, or one that is not JSON at all, falls
    back to the raw text and then to the reason phrase, so that a proxy or a
    misconfigured server in front of the service still produces a readable error.
    """
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail: Any = payload.get("detail") if isinstance(payload, Mapping) else None
    if isinstance(detail, list):
        detail = "; ".join(str(item) for item in detail)
    if detail is None:
        detail = (response.text or "").strip() or response.reason_phrase
    return LaunchwinError(
        f"{method} {url} returned HTTP {response.status_code}: {detail}",
        status_code=response.status_code,
        detail=detail,
        payload=payload,
        retry_after_s=response.headers.get("Retry-After"),
        method=method,
        url=url,
    )


# --------------------------------------------------------------------------
# The request bodies this module builds
# --------------------------------------------------------------------------


def _target_document(target: str | Mapping[str, Any]) -> dict[str, Any]:
    """The spec IV.1 target object, from a class name or from a target object.

    A string is upper cased so that ``"sso"`` and ``"SSO"`` are the same request, which
    keeps the citation identifier of a run reproducible whatever case the caller typed.
    A mapping is passed through unchanged, because a CUSTOM orbit carries numbers this
    module has no business inventing.
    """
    if isinstance(target, Mapping):
        document = {str(key): value for key, value in target.items()}
    else:
        name = str(target).strip()
        if not name:
            raise ValueError("target must name a spec IV.1 target type")
        document = {"type": name.upper()}
    if not document.get("type"):
        raise ValueError(
            "target must carry a type, one of LEO, POLAR, SSO or CUSTOM"
        )
    return document


def _date_range(dates: Sequence[str] | Mapping[str, str]) -> dict[str, str]:
    """The spec IV.1 date range, from a ``(start, end)`` pair or from a mapping.

    The order of the two dates is not checked here. Spec IV.1 does not define a range
    whose end precedes its start, and whether such a request is an empty answer or a
    422 is the service's decision to make from the frozen schema, not this module's.
    """
    if isinstance(dates, Mapping):
        missing = [key for key in ("start", "end") if not dates.get(key)]
        if missing:
            raise ValueError(f"the date range needs start and end; missing {missing}")
        return {"start": str(dates["start"]), "end": str(dates["end"])}
    try:
        start, end = dates
    except (TypeError, ValueError) as failure:
        raise ValueError(
            "dates must be a (start, end) pair of ISO dates, for example "
            '("2026-10-05", "2026-10-15")'
        ) from failure
    return {"start": str(start), "end": str(end)}


def _window_row(window: Mapping[str, Any]) -> dict[str, Any]:
    """One spec IV.1 window as one flat row of ``WINDOW_COLUMNS``."""
    row = {
        str(key): value
        for key, value in window.items()
        if key not in ("p_success_components", "screens")
    }
    components = window.get("p_success_components") or {}
    row.update(
        {column: components.get(field) for column, field in COMPONENT_COLUMNS.items()}
    )
    screens = window.get("screens") or {}
    row.update({column: screens.get(field) for column, field in SCREEN_COLUMNS.items()})
    return row