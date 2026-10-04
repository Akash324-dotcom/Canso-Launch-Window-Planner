"""``GET /v1/site``, spec IV.5, task A5 of issue #4.

The body is assembled from the site document the service actually read, so every
value on it carries the source string that document records. The document is
``backend/engine/data/site_canso.json`` when ENGINE has landed it and the API owned
copy until then, which is the precedence ``Settings.site_path`` already implements.

Spec IV.5 asks for two things this repository does not supply: the environmental
assessment reference URLs and the corridor polygon vertices used by the hazard test.
Neither appears in the specification with a value, in the integration contract, or in
any file this workflow owns, and an invented URL is exactly the kind of phantom
citation requirement 1 exists to prevent. Both are therefore absent, the absence is
asserted by ``backend/api/tests/test_site.py``, and the names to settle with ENGINE
are listed in ``docs/log/api.md``.

The frozen ``site_response.json`` leaves its root open, precisely because spec IV.5
enumerates the body in prose without field names (interpretation 14 of the G0 list),
so the extra fields below need no schema change. The names are still worth stating:
they are the API's proposal for the Seam 2 conversation, not an invention of values.
"""

from __future__ import annotations

from typing import Any

from backend.api.config import Settings

GEOMETRY_FIELDS = ("phi_s_deg", "lambda_s_deg", "h_s_m")

MISSING_FROM_SPECIFICATION = (
    "The environmental assessment reference URLs and the corridor polygon vertices "
    "used by the hazard test are named by spec IV.5 but no value for either appears "
    "in the specification, the integration contract or any document this workflow "
    "owns, so neither is claimed here. The names to be settled with ENGINE are "
    "listed in docs/log/api.md."
)


def build_site_response(settings: Settings, site_id: str | None = None) -> dict[str, Any]:
    """The spec IV.5 body for one site, assembled from the document just read."""
    from backend.api.provenance import constants_block_for

    resolved = site_id or settings.default_site
    path = settings.site_path(resolved)
    document = settings.site_document(resolved)
    site_config = settings.site_config

    body: dict[str, Any] = {
        "name": str(document["name"]),
        **{field: document[field] for field in GEOMETRY_FIELDS},
        "geometry_source": document["geometry_source"],
        "coordinate_variants_source": site_config["coordinate_variants_source"],
        "corridor": {
            "A_min_deg": document["corridor"]["A_min_deg"],
            "A_max_deg": document["corridor"]["A_max_deg"],
            "source": document["corridor"]["source"],
            "flag": document["corridor"]["flag"],
        },
        "operating_hours": document["operating_hours"],
        "operating_hours_source": document["operating_hours_source"],
        "car_references": list(document["car_references"]),
        "car_references_source": document["car_references_source"],
        "launch_rate_cap_per_year": site_config["launch_rate_cap_per_year"],
        "launch_rate_cap_source": site_config["launch_rate_cap_source"],
        "row_flags": dict(document.get("row_flags", {})),
        "source_files": [
            settings.relative(settings.constants_path),
            settings.relative(path),
            *([document["corridor_file"]] if "corridor_file" in document else []),
        ],
        "spec_gaps": MISSING_FROM_SPECIFICATION,
        "constants_block": constants_block_for(settings, kind=f"site:{resolved}"),
    }
    return body