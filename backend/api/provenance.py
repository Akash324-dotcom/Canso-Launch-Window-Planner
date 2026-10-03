"""Provenance machinery for the /v1 surface, tasks A1 of issue #4.

Spec IV defines two shared building blocks, ``constants_block`` and
``provenance_block``, that must appear on every result-bearing response. This
module builds both, and it builds them from files, not from literals: the
physical constants come from ``backend/api/data/constants.json`` and the site,
corridor and row flags come from the site document that the service actually
read, because spec II.10 requires that nothing site-, vehicle- or
criteria-dependent lives in source.

The ``citation_id`` is the run identifier of spec III.6: a deterministic hash of
the effective request, the constants and the service configuration, so that
``GET /v1/citation`` can later reproduce a stored run exactly. The date part of
the identifier is taken from the request's own ``date_range.start`` and never
from the clock, so the same request always produces the same identifier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from backend.api.config import Settings

citation_id_prefix = "run_"
CITATION_ID_DATE_FORMAT = "%Y%m%d"
CITATION_ID_HEX_LENGTH = 12

CONSTANT_NAMES = ("J2", "GM", "R_e", "omega_sid_rad_s", "gmst_model")
REQUIRED_CONSTANTS_FIELDS = (*CONSTANT_NAMES, "citation_id", "source")
REQUIRED_PROVENANCE_FIELDS = (
    "site",
    "corridor",
    "criteria_version",
    "vehicle_profile_id",
    "row_flags",
    "source_files",
)
UNSOURCED_REQUEST_OVERRIDE = "UNSOURCED_REQUEST_OVERRIDE"

SITE_PROVENANCE_FIELDS = ("name", "phi_s_deg", "lambda_s_deg", "h_s_m")


class ProvenanceIncomplete(AssertionError):
    """A response is missing a field of the spec IV shared blocks.

    Raised by ``assert_complete`` so that a provenance gap fails a test rather
    than reaching a client, which is what spec III.6 test 6 requires.
    """


@dataclass(frozen=True)
class Constants:
    """The physical constants as read from the configuration file."""

    values: dict[str, Any]
    sources: dict[str, str]
    config_path: Path

    def as_payload(self) -> dict[str, Any]:
        """The hashed form of the constants: values and their recorded sources."""
        return {
            "values": dict(self.values),
            "sources": dict(self.sources),
        }


def load_constants(settings: Settings | None = None) -> Constants:
    """Read the constants block inputs from ``backend/api/data/constants.json``."""
    path = settings.constants_path if settings else Path(__file__).resolve().parent / "data" / "constants.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    values = document["values"]
    sources = document["sources"]
    missing = [name for name in CONSTANT_NAMES if name not in values or name not in sources]
    if missing:
        raise ValueError(f"{path} does not define a value and a source for {missing}")
    return Constants(values=dict(values), sources=dict(sources), config_path=path)


# ---------------------------------------------------------------- canonical JSON


def canonical_json(payload: Any) -> str:
    """Deterministic JSON text: sorted keys, no insignificant whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_of(payload: Any) -> str:
    """Lowercase hexadecimal SHA-256 of the canonical JSON of ``payload``."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def config_hash(config_payload: Any) -> str:
    """The configuration half of the citation hash, exposed for the citation record."""
    return sha256_of(config_payload)


def make_citation_id(
    effective_request: Any,
    constants_payload: Any,
    config_payload: Any,
    date_start: str,
) -> str:
    """Deterministic run identifier: ``run_YYYYMMDD_`` plus twelve hex digits.

    The date is the request's own ``date_range.start``, not the current date, so
    that repeating a request repeats the identifier. The digest covers the
    effective request, the constants and the configuration, so a different
    criteria version, a different constant or a different configuration gives a
    different identifier.
    """
    digest = sha256_of(
        {
            "constants": constants_payload,
            "config": config_payload,
            "request": effective_request,
        }
    )
    day = date_start.replace("-", "")
    return f"{citation_id_prefix}{day}_{digest[:CITATION_ID_HEX_LENGTH]}"


# ------------------------------------------------------------------- the blocks


def build_constants_block(constants: Constants, citation_id: str) -> dict[str, Any]:
    """Spec IV ``constants_block``: every constant, its source, and the run id."""
    return {
        **{name: constants.values[name] for name in CONSTANT_NAMES},
        "citation_id": citation_id,
        "source": {name: constants.sources[name] for name in CONSTANT_NAMES},
    }


def build_provenance_block(
    site: str,
    site_document: dict[str, Any],
    corridor_override: dict[str, Any] | None,
    criteria_version: str,
    vehicle_profile_id: str,
    source_files: Iterable[str],
) -> dict[str, Any]:
    """Spec IV ``provenance_block``, filled from the document that was read.

    A corridor bound supplied in the request replaces the configured one and is
    then flagged as unsourced, because the request carries no citation for it.
    """
    configured_corridor = dict(site_document["corridor"])
    corridor = {
        "A_min_deg": configured_corridor["A_min_deg"],
        "A_max_deg": configured_corridor["A_max_deg"],
        "source": configured_corridor["source"],
        "flag": configured_corridor["flag"],
    }
    row_flags = dict(site_document.get("row_flags", {}))
    override = corridor_override or {}
    for bound in ("A_min_deg", "A_max_deg"):
        if override.get(bound) is not None:
            corridor[bound] = override[bound]
            corridor["source"] = "request override; the request carries no citation for this bound"
            corridor["flag"] = UNSOURCED_REQUEST_OVERRIDE
            row_flags[f"corridor_{bound}"] = UNSOURCED_REQUEST_OVERRIDE

    site_block = {name: site_document[name] for name in SITE_PROVENANCE_FIELDS if name in site_document}
    site_block["name"] = site
    return {
        "site": site_block,
        "corridor": corridor,
        "criteria_version": criteria_version,
        "vehicle_profile_id": vehicle_profile_id,
        "row_flags": row_flags,
        "source_files": list(source_files),
    }


def resolve_criteria_version(settings: Settings, requested: str | None) -> str:
    """The criteria version to record: the request's, else the configured default.

    WEATHER owns ``backend/weather/data/criteria_v1.json``. When that file is
    present its declared version wins, so the recorded version is the one whose
    rows were actually read.
    """
    criteria_file = settings.criteria_file
    if criteria_file.is_file():
        document = json.loads(criteria_file.read_text(encoding="utf-8"))
        declared = document.get("version") or document.get("criteria_version")
        if isinstance(declared, str) and requested is None:
            return declared
    return requested or settings.default_criteria_version


# ------------------------------------------------------------------- assertions


def missing_provenance_fields(body: dict[str, Any]) -> list[str]:
    """Every spec IV provenance field absent from ``body``, as ``block.field`` names."""
    missing: list[str] = []
    for block_name in ("constants_block", "provenance_block"):
        block = body.get(block_name)
        required = REQUIRED_CONSTANTS_FIELDS if block_name == "constants_block" else REQUIRED_PROVENANCE_FIELDS
        if not isinstance(block, dict):
            missing.extend(f"{block_name}.{name}" for name in required)
            continue
        missing.extend(f"{block_name}.{name}" for name in required if block.get(name) is None)
    return missing


def assert_complete(body: dict[str, Any]) -> None:
    """Raise ``ProvenanceIncomplete`` unless both shared blocks are fully present."""
    missing = missing_provenance_fields(body)
    if missing:
        raise ProvenanceIncomplete(f"response is missing provenance fields: {missing}")


# -------------------------------------------------------------------- stamping


def stamp_provenance(
    engine_body: dict[str, Any],
    settings: Settings,
    effective_request: dict[str, Any],
    source_files: Iterable[str] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Stamp both shared blocks onto an engine body and return it with its sources.

    The engine returns the response body of spec IV.1 minus the constants and
    provenance blocks, which are API's to add. The identifier is computed from
    the effective request, the constants and the service configuration, and the
    recorded ``source_files`` are exactly the files this call read.
    """
    site_id = str(effective_request["site"])
    site_document = settings.site_document(site_id)
    constants = load_constants(settings)

    read = [settings.relative(constants.config_path), settings.relative(settings.service_path)]
    read.append(settings.relative(settings.site_path(site_id)))
    criteria_file = settings.criteria_file
    if criteria_file.is_file():
        read.append(settings.relative(criteria_file))
    engine_owned = settings.vehicle_profile_path(str(effective_request["vehicle_profile_id"]))
    if engine_owned.is_file():
        read.append(settings.relative(engine_owned))
    for extra in source_files:
        if extra not in read:
            read.append(extra)

    date_start = str(effective_request["date_range"]["start"])
    criteria_version = resolve_criteria_version(settings, effective_request.get("criteria_version"))
    citation = make_citation_id(
        effective_request=effective_request,
        constants_payload=constants.as_payload(),
        config_payload=settings.service,
        date_start=date_start,
    )

    stamped = dict(engine_body)
    stamped["constants_block"] = build_constants_block(constants, citation_id=citation)
    stamped["provenance_block"] = build_provenance_block(
        site=site_id,
        site_document=site_document,
        corridor_override=effective_request.get("corridor"),
        criteria_version=criteria_version,
        vehicle_profile_id=str(effective_request["vehicle_profile_id"]),
        source_files=read,
    )
    return stamped, read