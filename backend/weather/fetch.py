"""Forecast acquisition: Open-Meteo parsing, model run time, explicit units, disk cache and fallback chain.

Every forecast returned by this module carries forecast_issue_time, the source that answered, and the time it
was retrieved. A snapshot read from disk keeps its original issue time, so a cached answer is never presented
as a fresh fetch (spec IV.8).
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import config, criteria, units
from .errors import WeatherDataError

CACHE_DIR = Path(__file__).resolve().parent / "cache"
SNAPSHOT_DIR = config.DATA_DIR / "snapshot"
OFFLINE_ENV = "LAUNCHWIN_WEATHER_OFFLINE"

_TRANSPORT: httpx.BaseTransport | None = None
_MEMO: dict = {}
_MEMBER = re.compile(r"^(?P<parameter>.+)_member(?P<number>\d+)$")


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Install the HTTP transport used for every request. Tests install a mock; None restores the default."""
    global _TRANSPORT
    _TRANSPORT = transport


def clear_memo() -> None:
    """Forget every in-process cached forecast."""
    _MEMO.clear()


def offline() -> bool:
    """True when live sources are disabled by the environment (offline demo, tests)."""
    return os.environ.get(OFFLINE_ENV, "").strip().lower() in {"1", "true", "yes"}


def iso_z(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def cache_path(site: str, forecast_issue_time: str, source_id: str) -> Path:
    """Disk location of one raw fetch. The key is (site, forecast_issue_time); a new run gets a new folder."""
    stamp = parse_iso_z(forecast_issue_time).strftime("%Y%m%dT%H%MZ")
    return CACHE_DIR / site / stamp / f"{source_id}.json"


# Parsing ---------------------------------------------------------------------------------------------------

def parse_open_meteo(payload: dict) -> dict:
    """Turn an Open-Meteo hourly payload, deterministic or ensemble, into members in evaluation units.

    Returns times (UTC, 'YYYY-MM-DDTHH:MM'), members (one mapping of parameter to hourly values per member),
    member_labels, units (parameter to evaluation unit) and the grid cell. A column that is entirely null is
    kept as nulls with unit None, so that a caller can tell 'field not provided' from 'field provided'.
    """
    if payload.get("utc_offset_seconds", 0) != 0:
        raise WeatherDataError("payload is not in UTC; request timezone=GMT")
    hourly = payload["hourly"]
    source_units = payload["hourly_units"]
    times = list(hourly["time"])
    columns: dict[str, dict[int, list]] = {}
    out_units: dict[str, str | None] = {}
    for key, values in hourly.items():
        if key == "time":
            continue
        match = _MEMBER.match(key)
        parameter, number = (match["parameter"], int(match["number"])) if match else (key, 0)
        if len(values) != len(times):
            raise WeatherDataError(f"column {key} has {len(values)} values for {len(times)} times")
        if all(value is None for value in values):
            converted, unit = [None] * len(values), None
        else:
            unit = units.canonical_unit(source_units[key])
            converted = [None if value is None else units.convert(value, source_units[key], unit)
                         for value in values]
        columns.setdefault(parameter, {})[number] = converted
        if unit is not None or parameter not in out_units:
            out_units[parameter] = unit
    numbers = sorted({number for by_member in columns.values() for number in by_member})
    blank = [None] * len(times)
    members = [{parameter: by_member.get(number, blank) for parameter, by_member in columns.items()}
               for number in numbers]
    labels = ["control" if number == 0 else f"member{number:02d}" for number in numbers]
    grid = {key: payload.get(key) for key in ("latitude", "longitude", "elevation")}
    return {"times": times, "members": members, "member_labels": labels, "units": out_units, "grid": grid}


def missing_parameters(parsed: dict, parameters: list[str]) -> list[str]:
    """The requested parameters for which the payload provides no value at all."""
    absent = []
    for parameter in parameters:
        provided = any(value is not None for member in parsed["members"] for value in member.get(parameter, []))
        if not provided:
            absent.append(parameter)
    return absent


# Acquisition -----------------------------------------------------------------------------------------------

def default_parameters(site: str, chain: str = "ensemble") -> list[str]:
    """The fields a chain must supply for the current criteria version: its share of the evaluated rows."""
    from . import climatology

    split = climatology.split_rows(site, criteria.load_criteria(None))
    supplement_chain = config.load_sources()["supplement"]["chain"]
    return criteria.required_parameters(split["supplement"] if chain == supplement_chain else split["primary"])


def fetch_forecast(site: str, chain: str = "ensemble", parameters: list[str] | None = None,
                   now: datetime | None = None) -> dict | None:
    """Walk the named fallback chain of data/sources.json and return the first complete forecast, or None.

    The result records which source answered ('source', a spec IV.3 value) and always carries
    forecast_issue_time. None means no source could supply every requested parameter; the caller then lets
    climatology carry the date. Nothing is invented.
    """
    site_cfg = config.load_site(site)
    sources = config.load_sources()
    request = sources["request"]
    parameters = list(parameters) if parameters is not None else default_parameters(site, chain)
    now = now or datetime.now(timezone.utc)

    key = (site, chain, tuple(parameters))
    held = _MEMO.get(key)
    if held is not None:
        age = time.monotonic() - held[0]
        live = held[1] is not None and held[1]["source"] != "snapshot_cache"
        ttl = request["refresh_ttl_s"] if live else request["failure_retry_s"]
        if age < ttl:
            return held[1]

    chain_ids = sources["chains"][chain]
    kinds = [sources["sources"][source_id]["kind"] for source_id in chain_ids]
    live_kind = next((kind for kind in kinds if kind != "snapshot"), None)
    forecast = None
    for source_id in chain_ids:
        source = sources["sources"][source_id]
        if source["kind"] == "snapshot":
            forecast = _latest_snapshot(site, live_kind, parameters)
        elif not offline():
            try:
                forecast = _fetch_live(source_id, source, site, site_cfg, parameters, now, request)
            except (httpx.HTTPError, WeatherDataError, KeyError, ValueError):
                forecast = None
        if forecast is not None:
            break
    _MEMO[key] = (time.monotonic(), forecast)
    return forecast


def _client(timeout_s: float) -> httpx.Client:
    return httpx.Client(transport=_TRANSPORT, timeout=timeout_s)


def _issue_time(source: dict, now: datetime, request: dict) -> tuple[str, str]:
    """The model run time from the source's metadata endpoint, or the fetch time if that cannot be trusted.

    The metadata is trusted when the run time is not in the future and the record's own data_end_time has not
    passed. A record whose data has ended describes an old run, whatever the data endpoint serves today.
    """
    stamped = (iso_z(now.replace(minute=0, second=0, microsecond=0)), "fetch_time")
    try:
        with _client(request["timeout_s"]) as client:
            response = client.get(source["meta_url"])
        response.raise_for_status()
        record = response.json()
        run = datetime.fromtimestamp(int(record["last_run_initialisation_time"]), timezone.utc)
        data_end = datetime.fromtimestamp(int(record["data_end_time"]), timezone.utc)
    except (httpx.HTTPError, KeyError, ValueError, TypeError):
        return stamped
    if run > now or data_end < now:
        return stamped
    return iso_z(run), "model_run_initialisation"


def _fetch_live(source_id: str, source: dict, site: str, site_cfg: dict, parameters: list[str],
                now: datetime, request: dict) -> dict:
    issue_time, basis = _issue_time(source, now, request)
    path = cache_path(site, issue_time, source_id)
    stored = None
    if basis == "model_run_initialisation" and path.is_file():
        held = json.loads(path.read_text(encoding="utf-8"))
        if all(parameter in held["payload"].get("hourly_units", {}) for parameter in parameters):
            stored = held
    if stored is None:
        params = {
            "latitude": site_cfg["latitude_deg"],
            "longitude": site_cfg["longitude_deg"],
            "hourly": ",".join(parameters),
            "models": source["model"],
            "forecast_days": request["forecast_days"],
            "timezone": "GMT",
        }
        with _client(request["timeout_s"]) as client:
            response = client.get(source["url"], params=params)
        response.raise_for_status()
        meta = {
            "site": site,
            "source_id": source_id,
            "kind": source["kind"],
            "model": source["model"],
            "response_source": source["response_source"],
            "forecast_issue_time": issue_time,
            "issue_time_basis": basis,
            "retrieved_at": iso_z(now),
            "url": source["url"],
            "request_params": params,
        }
        stored = {"meta": meta, "payload": response.json()}
        forecast = _assemble(stored, stored["meta"]["response_source"], parameters)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stored, separators=(",", ":")), encoding="utf-8")
        return forecast
    return _assemble(stored, stored["meta"]["response_source"], parameters)


def _assemble(stored: dict, response_source: str, parameters: list[str]) -> dict:
    parsed = parse_open_meteo(stored["payload"])
    absent = missing_parameters(parsed, parameters)
    if absent:
        raise WeatherDataError(f"{stored['meta']['source_id']} provides no values for {absent}")
    meta = stored["meta"]
    return {
        "site": meta["site"],
        "source_id": meta["source_id"],
        "source": response_source,
        "kind": meta["kind"],
        "model": meta["model"],
        "forecast_issue_time": meta["forecast_issue_time"],
        "issue_time_basis": meta["issue_time_basis"],
        "retrieved_at": meta["retrieved_at"],
        **parsed,
    }


def snapshot_files(site: str) -> list[Path]:
    """Every stored forecast for a site: the live cache and the committed snapshot directory."""
    found = sorted((CACHE_DIR / site).glob("*/*.json")) if (CACHE_DIR / site).is_dir() else []
    if (SNAPSHOT_DIR / site).is_dir():
        found += sorted((SNAPSHOT_DIR / site).glob("*.json"))
    return found


def _latest_snapshot(site: str, kind: str | None, parameters: list[str]) -> dict | None:
    """The most recently issued stored forecast of the wanted kind that supplies every requested parameter."""
    candidates = []
    for path in snapshot_files(site):
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            meta = stored["meta"]
            if kind is not None and meta["kind"] != kind:
                continue
            candidates.append((meta["forecast_issue_time"], meta["retrieved_at"], str(path), stored))
        except (OSError, ValueError, KeyError):
            continue
    for _, _, _, stored in sorted(candidates, key=lambda item: item[:3], reverse=True):
        try:
            return _assemble(stored, "snapshot_cache", parameters)
        except (WeatherDataError, KeyError, ValueError):
            continue
    return None
