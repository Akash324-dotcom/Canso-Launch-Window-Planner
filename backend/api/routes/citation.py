"""``GET /v1/citation``, spec IV.6, task A6 of issue #4.

The researcher interface. The route reads the stored record of one run and serves it,
so the constants, the configuration hash, the criteria version, the vehicle rows with
their flags, the source files, the engine version and the request that produced the
run all come back exactly as the run saw them. Spec III.6 test 6 clause (c) asks for
exactly that.

An identifier no run stored is a 404 whose detail says the run was not found. That is
a genuine resource miss and not a domain outcome, which is the distinction spec IV.7
rule 2 draws.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from backend.api import citation as run_store
from backend.api.config import Settings, get_settings
from backend.api.limits import READ_BUCKET
from backend.api.middleware import cached_response, rate_limited
from backend.api.publish import get_query_extra, query_parameter

router = APIRouter(tags=["citation"])

DESCRIPTION = (
    "Machine-readable constants and data provenance for one stored run, spec IV.6: "
    "the spec II.10 table serialised, plus the constants, the configuration hash, the "
    "criteria version, the vehicle rows with their flags, the source files, the "
    "engine version and the request."
)


@router.get(
    "/citation",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "id",
                {"type": "string", "minLength": 1},
                True,
                "The citation identifier of a run, of the form run_YYYYMMDD_hex.",
            )
        ],
        DESCRIPTION,
    ),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_citation(
    request: Request,
    id: str = Query(..., description="The citation identifier of a stored run."),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The provenance of one stored run, spec IV.6."""
    return cached_response(request, lambda: run_store.read_run(settings, id))