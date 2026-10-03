"""The two weather read endpoints, tasks A4 of issue #4.

``GET /v1/weather/probability`` is spec IV.3 and ``GET /v1/validation/skill`` is
spec IV.4. Both are thin: validate the query, ask ``backend.api.weather`` for the
body, publish the frozen schema in the OpenAPI document, and stamp the constants
block that spec IV requires on every result-bearing response. Neither route composes
a number, and neither turns a weather condition into an HTTP error that spec IV.7
rule 2 does not name.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from backend.api.cache import CacheRegistry
from backend.api.config import Settings, get_settings
from backend.api.limits import READ_BUCKET
from backend.api.middleware import cached_response, rate_limited
from backend.api.publish import get_query_extra, query_parameter
from backend.api.schemas import errors_for
from backend.api.weather import probability_document, skill_document

router = APIRouter(tags=["weather"])

WEATHER_SCHEMA = "weather_probability_response"
SKILL_SCHEMA = "skill_response"

PROBABILITY_DESCRIPTION = (
    "The launch probability for one date and site, spec IV.3. Served from the live "
    "weather layer when it exists, otherwise from the recorded offline snapshot, "
    "which is echoed with the forecast issue time it was issued at."
)
SKILL_DESCRIPTION = (
    "The hindcast verification skill series, reliability bins and ROC points for one "
    "period, spec IV.4. The series is truncated to lead_max."
)


def _registry(request: Request) -> CacheRegistry:
    return request.app.state.cache_registry


@router.get(
    "/weather/probability",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "date",
                {"type": "string", "format": "date"},
                True,
                "The day the probability applies to, YYYY-MM-DD.",
            ),
            query_parameter(
                "site",
                {"type": "string", "default": "canso"},
                False,
                "A named site in configuration. Defaults to the configured site.",
            ),
        ],
        PROBABILITY_DESCRIPTION,
        schema_name=WEATHER_SCHEMA,
    ),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_weather_probability(
    request: Request,
    date: str = Query(..., description="The day the probability applies to, YYYY-MM-DD."),
    site: str | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """One launch probability, spec IV.3."""

    def build() -> dict[str, Any]:
        return probability_document(
            settings,
            _registry(request),
            date,
            site or settings.default_site,
            settings.default_criteria_version,
        )

    return cached_response(request, build)


@router.get(
    "/validation/skill",
    openapi_extra=get_query_extra(
        [
            query_parameter(
                "period_start",
                {"type": "string", "format": "date"},
                True,
                "First day of the verification period, YYYY-MM-DD.",
            ),
            query_parameter(
                "period_end",
                {"type": "string", "format": "date"},
                True,
                "Last day of the verification period, YYYY-MM-DD.",
            ),
            query_parameter(
                "lead_max",
                {"type": "integer", "minimum": 0, "default": 10},
                False,
                "Largest lead time in days to report. Defaults to the configured value.",
            ),
        ],
        SKILL_DESCRIPTION,
        schema_name=SKILL_SCHEMA,
    ),
    dependencies=[Depends(rate_limited(READ_BUCKET))],
)
def get_validation_skill(
    request: Request,
    period_start: str = Query(..., description="First day of the verification period."),
    period_end: str = Query(..., description="Last day of the verification period."),
    lead_max: int | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """The hindcast skill series, spec IV.4."""
    resolved_lead_max = settings.skill_config["default_lead_max"] if lead_max is None else lead_max

    def build() -> dict[str, Any]:
        document = skill_document(
            settings, _registry(request), period_start, period_end, int(resolved_lead_max)
        )
        violations = errors_for(SKILL_SCHEMA, document)
        if violations:
            raise ValueError(
                "the skill document does not satisfy the frozen contract: "
                f"{[error.message for error in violations]}"
            )
        return document

    return cached_response(request, build)