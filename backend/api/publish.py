"""Publish the frozen schemas of gate G0 in the OpenAPI document.

The generated FastAPI schema for these routes would describe free-form objects,
because the frozen contract is the authority. Publishing the frozen files keeps a
reader of ``/v1/openapi.json`` on exactly the same contract as a reader of
``tests/contract``, which is the whole point of Seam 2.
"""

from __future__ import annotations

from typing import Any

from backend.api.schemas import load_schemas


def frozen_responses(schema_name: str, description: str) -> dict[str, Any]:
    schemas, _ = load_schemas()
    return {
        "200": {"description": description, "content": {"application/json": {"schema": schemas[schema_name]}}},
        "404": {"description": "Unknown orbit, site or run id."},
        "422": {"description": "The request does not satisfy the frozen contract."},
        "429": {"description": "Rate limit exceeded. Retry-After is set."},
        "503": {
            "description": (
                "An upstream layer is unreachable and the offline fixture path "
                "answers instead. Retry-After is set and the body names the path."
            )
        },
    }


def get_query_extra(
    parameters: list[dict[str, Any]],
    description: str,
    schema_name: str | None = None,
) -> dict[str, Any]:
    success: dict[str, Any] = {"description": description}
    if schema_name is not None:
        schemas, _ = load_schemas()
        success["content"] = {"application/json": {"schema": schemas[schema_name]}}
    return {
        "parameters": parameters,
        "responses": {
            "200": success,
            "404": {"description": "Unknown orbit, site or run id."},
            "422": {"description": "The request does not satisfy the frozen contract."},
            "429": {"description": "Rate limit exceeded. Retry-After is set."},
            "503": {
                "description": (
                    "The weather layer is unreachable and the recorded offline "
                    "document answers instead, or cannot. Retry-After is set and "
                    "the body names the path."
                )
            },
        },
    }


def query_parameter(
    name: str,
    schema: dict[str, Any],
    required: bool,
    description: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": schema,
    }