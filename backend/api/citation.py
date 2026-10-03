"""The researcher interface: stored runs and ``GET /v1/citation``, spec IV.6.

Spec IV.6 says the citation body is the spec II.10 provenance table serialised, which
is what this module produces: one item per row of that table, each with its value or
source, whether it is hard-coded or dynamic, the file or endpoint it came from and
its citation. The table itself lives in ``backend/api/data/provenance_table.json``
rather than in this module, because spec II.10 states the rule of construction: any
number that appears in a result and is not computed from that table is a bug.

The store is one JSON document per run under the configured runs directory, named by
the citation identifier, written on every ``POST /v1/windows``. The identifier is the
deterministic hash of task A1, so writing a run twice overwrites the same document
rather than accumulating copies, and a restart loses nothing.

``tests/contract/schemas/citation_response.json`` does not exist and is not created
here. Gate G0 froze the contract and the citation body was not in its file list (G0
interpretation 23), so the shape is asserted in ``backend/api/tests/test_citation.py``
against spec IV.6 field by field, and the proposal for a frozen schema is recorded in
``docs/log/api.md`` for the next Seam 2 announcement.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Iterable

from backend.api.config import Settings
from backend.api.errors import ContractViolation, UnknownResourceError
from backend.api.orbits import RegisteredOrbit

RUN_RESOURCE_KIND = "run"
STORE_SCHEMA_VERSION = "launchwin-run-record-1"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def config_hash(settings: Settings) -> str:
    """The configuration half of the run identifier, exposed on the citation."""
    from backend.api.provenance import config_hash as digest

    return digest(settings.service)


def vehicle_rows(settings: Settings, vehicle_profile_id: str) -> list[dict[str, Any]]:
    """The vehicle rows the run read, each with its own row flag.

    ENGINE owns ``backend/engine/data/vehicles/*.json``. Until that file exists the
    list is empty and nothing is invented: an absent row is reported as absent, which
    is the point of spec II.10, and the path the file will appear at is still resolved
    so that it is listed the moment it exists.
    """
    path = settings.vehicle_profile_path(vehicle_profile_id)
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("rows", [])
    return [
        {**row, "flag": row.get("flag", row.get("row_flag", "ASSUMPTION"))} for row in rows
    ]


def build_run_record(
    settings: Settings,
    body: dict[str, Any],
    effective_request: dict[str, Any],
    constants_block: dict[str, Any],
    provenance_block: dict[str, Any],
    engine_version: str,
    orbit_id: str | None,
) -> dict[str, Any]:
    """The stored record of one run, which is also what the citation endpoint serves."""
    citation_id = str(constants_block["citation_id"])
    criteria_version = str(provenance_block["criteria_version"])
    rows = vehicle_rows(settings, str(effective_request["vehicle_profile_id"]))
    return {
        "record_schema": STORE_SCHEMA_VERSION,
        "citation_id": citation_id,
        "run_id": citation_id,
        "orbit_id": orbit_id,
        "engine_version": engine_version,
        "generated_at": utc_now(),
        "config_hash": config_hash(settings),
        "criteria_version": criteria_version,
        "constants": {
            name: constants_block[name]
            for name in ("J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model")
        },
        "constants_sources": dict(constants_block["source"]),
        "constants_block": constants_block,
        "provenance_block": provenance_block,
        "vehicle_profile_id": str(effective_request["vehicle_profile_id"]),
        "vehicle_rows": rows,
        "source_files": list(provenance_block["source_files"]),
        "request": effective_request,
        "request_body": body,
        "items": provenance_items(
            settings,
            constants_block=constants_block,
            provenance_block=provenance_block,
            criteria_version=criteria_version,
            engine_version=engine_version,
            rows=rows,
            orbit_id=orbit_id,
            request=effective_request,
        ),
        "bibtex": bibtex(citation_id, criteria_version, engine_version),
    }


def write_run(settings: Settings, record: dict[str, Any]) -> None:
    """Store one run record. The directory is created because it is git empty."""
    directory = settings.runs_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = settings.run_record_path(str(record["citation_id"]))
    path.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_run(settings: Settings, citation_id: str) -> dict[str, Any]:
    """The stored record of one run, or a 404 that says the run was not found."""
    validate_citation_id(settings, citation_id)
    path = settings.run_record_path(citation_id)
    if not path.is_file():
        raise UnknownResourceError(
            RUN_RESOURCE_KIND,
            citation_id,
            detail=f"the run with citation id {citation_id!r} was not found in the store at "
            f"{settings.relative(settings.runs_dir)}",
        )
    return json.loads(path.read_text(encoding="utf-8"))


CITATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_citation_id(settings: Settings, citation_id: str) -> None:
    """Refuse an identifier that is not a plain token, before touching the filesystem.

    The store is looked up by path, so an identifier carrying a separator or a parent
    reference could address a document outside the runs directory. Every identifier
    this service mints matches the pattern by construction, so anything else is a
    malformed request rather than a miss, and the containment check is kept as well so
    that the guarantee does not rest on the pattern alone.
    """
    if not CITATION_ID_PATTERN.fullmatch(citation_id or ""):
        raise ContractViolation(
            "id must be a citation identifier such as run_20261005_0123456789ab, carrying no "
            "path separator and no parent reference",
            schema_name="citation_response",
            violations=[f"/id: {citation_id!r} is not a citation identifier"],
        )
    if settings.run_record_path(citation_id).parent.resolve() != settings.runs_dir.resolve():
        raise ContractViolation(
            f"the citation id {citation_id!r} does not address a record inside the run store",
            schema_name="citation_response",
            violations=[f"/id: {citation_id!r} resolves outside the run store"],
        )


def stored_runs(settings: Settings) -> list[dict[str, Any]]:
    """Every stored record, in citation identifier order."""
    directory = settings.runs_dir
    if not directory.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return records


def stored_orbits(settings: Settings) -> list[RegisteredOrbit]:
    """The custom orbit ids found in the stored records.

    This is what makes an id created by a POST resolvable after a restart, which the
    in-memory registry alone cannot do. Only ids that name no published class are
    listed: a preset id is served from its own recorded segment and never needs a
    record to exist.
    """
    from backend.api.orbits import match_preset

    found: list[RegisteredOrbit] = []
    for record in stored_runs(settings):
        request = record.get("request") or {}
        target = request.get("target") or {}
        orbit_id = record.get("orbit_id")
        inclination = target.get("i_t_deg")
        if not orbit_id or not isinstance(inclination, (int, float)):
            continue
        if match_preset(settings, float(inclination)) is not None:
            continue
        altitude = target.get("h_t_km")
        found.append(
            RegisteredOrbit(
                orbit_id=str(orbit_id),
                i_t_deg=float(inclination),
                h_t_km=None if altitude is None else float(altitude),
                preset=None,
                citation_id=str(record.get("citation_id") or ""),
                source_files=tuple(record.get("source_files", ())),
            )
        )
    return found


# ------------------------------------------------------------ the II.10 table


def provenance_items(
    settings: Settings,
    constants_block: dict[str, Any],
    provenance_block: dict[str, Any],
    criteria_version: str,
    engine_version: str,
    rows: Iterable[dict[str, Any]],
    orbit_id: str | None,
    request: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The spec II.10 table, one serialised row per entry, for this run.

    ``value_or_source`` and ``file_or_endpoint`` may name a runtime value. Where one
    does, the value is substituted from the run rather than from the table, because
    the table records which quantity is dynamic and the run records what it was.
    """
    runtime: dict[str, Any] = {
        "constants_block": constants_block,
        "provenance_block": provenance_block,
        "criteria_version": criteria_version,
        "engine_version": engine_version,
        "vehicle_rows": list(rows),
        "source_files": list(provenance_block["source_files"]),
        "orbit_id": orbit_id,
        "request": dict(request or {}),
    }
    items: list[dict[str, Any]] = []
    for row in settings.provenance_table["items"]:
        items.append(
            {
                "item": row["item"],
                "value_or_source": _resolve(runtime, row.get("runtime_key"), row.get("value_or_source")),
                "hard_coded_or_dynamic": row["hard_coded_or_dynamic"],
                "file_or_endpoint": _resolve(
                    runtime, row.get("runtime_endpoint_key"), row["file_or_endpoint"]
                ),
                "citation": row["citation"],
            }
        )
    return items


def _resolve(runtime: dict[str, Any], dotted_key: Any | None, fallback: Any) -> Any:
    """Follow a dotted key into the run, falling back to the table's own value.

    A dotted key keeps the table readable: ``provenance_block.site`` says which field
    of the run fills that row, without this module hard-coding the shape of the
    provenance block.
    """
    if not isinstance(dotted_key, str) or not dotted_key:
        return fallback
    current: Any = runtime
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return fallback
        current = current[part]
    return current


def bibtex(citation_id: str, criteria_version: str, engine_version: str) -> str:
    """The BibTeX entry spec IV.6 asks for alongside the table.

    It carries only what this run used. No external identifier is written here,
    because the repository holds none that was resolved by title, and an invented DOI
    is the failure mode requirement 1 exists to prevent.
    """
    year = citation_id.split("_")[1] if citation_id.count("_") >= 2 else ""
    return (
        "@misc{launchwin_run,\n"
        f"  title = {{Launch window run {citation_id}}},\n"
        f"  note = {{criteria version {criteria_version}, engine version {engine_version}}},\n"
        f"  year = {{{year}}},\n"
        "  howpublished = {Canso launch window decision engine, GET /v1/citation}\n"
        "}"
    )