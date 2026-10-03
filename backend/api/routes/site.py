"""``GET /v1/site``, spec IV.5, task A5 of issue #4.

A thin route over ``backend.api.site``: it resolves the site id, assembles the body
from the document that was read, and publishes the frozen schema. An unknown site
id is a 404, which spec IV.7 rule 2 reserves for exactly that case and which the A1
machinery already established on the window route.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from backend.api.config import Settings, get_settings
from backend.api.limits import READ_BUCKET
from backend.api.middleware import cached_response, rate_limited
from backend.api.publish import get_query_extra, query_parameter
from backend.api.site import build_site_response

router = APIRouter(tags=["site"])

SITE_SCHEMA = "site_response"

DESCRIPTION = (
    "Site geometry with sources, corridor bounds with their source and assumption "
    "flag, CAR references, operating hours and the launch rate cap, spec IV.5. "
    "Read from the site document the service actually read."
)


@router.get(
    "/site",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "site",
                {"type": "string", "default": "canso"},
                False,
                "A named site in configuration. Defaults to the configured site.",
            )
        ],
        DESCRIPTION,
        schema_name=SITE_SCHEMA,
    ),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_site(
    request: Request,
    site: str | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """One site record, spec IV.5."""
    return cached_response(request, lambda: build_site_response(settings, site))