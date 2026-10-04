"""Cross-origin access to the service, which the static frontend needs.

``frontend/src/config.js`` points ``API_BASE`` at ``http://localhost:8000/v1`` while the
page is served by a static file server on another port. Those are two origins, so every
call the page makes is a cross-origin request: the browser sends a preflight and, when
the service answers without the CORS headers, blocks the response. The frontend treats
the blocked call as an unreachable service and falls back to the committed fixtures
behind the OFFLINE banner. Nothing appears in the service log, because the block is the
browser's and the service answered normally.

The seven tests are the seven of the issue. Six of them fail when the
``add_middleware`` call in ``create_app`` is removed. The seventh, the same-origin
check, passes with and without the middleware on purpose: it proves that adding the
layer changes nothing for a request that never was cross-origin.

The wildcard is deliberate and demo-only. The service has no authentication and sends
no cookie, so ``allow_origins=["*"]`` with ``allow_credentials=False`` exposes nothing.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings

# The origin of the page: a static file server on a port that is not the API's.
STATIC_PAGE_ORIGIN = "http://localhost:5500"
UNRELATED_ORIGIN = "https://example.invalid"

# The arguments the issue specifies for add_middleware, and no others.
EXPECTED_CORS_ARGUMENTS = {
    "allow_origins": ["*"],
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    "allow_credentials": False,
}

ALLOW_ORIGIN = "access-control-allow-origin"
ALLOW_METHODS = "access-control-allow-methods"
ALLOW_HEADERS = "access-control-allow-headers"


def cors_arguments(application: FastAPI) -> dict[str, Any] | None:
    """The keyword arguments the CORSMiddleware was installed with, or None.

    Starlette keeps the arguments of ``add_middleware`` on the ``Middleware`` wrapper,
    so this reads what the service asked for instead of inferring it from a response.
    """
    for middleware in application.user_middleware:
        if middleware.cls is CORSMiddleware:
            return dict(middleware.kwargs)
    return None


@pytest.fixture()
def application(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture()
def browser(application: FastAPI) -> Iterator[TestClient]:
    """A client that sends what a browser sends; each test adds its own Origin."""
    with TestClient(application) as test_client:
        yield test_client


def test_the_cors_middleware_is_installed_with_the_expected_arguments(
    application: FastAPI,
) -> None:
    arguments = cors_arguments(application)

    assert arguments is not None, (
        "create_app installs no CORSMiddleware, so a browser on the static page's "
        "origin blocks every call to /v1 and the page falls back to fixtures"
    )
    assert arguments == EXPECTED_CORS_ARGUMENTS
    assert arguments["allow_credentials"] is False, (
        "a wildcard origin together with credentials is refused by browsers, and "
        "this service has no credentials to send"
    )


def test_a_preflight_options_request_is_answered(browser: TestClient) -> None:
    """The preflight is the request that fails first in the browser."""
    response = browser.options(
        "/v1/windows",
        headers={
            "Origin": STATIC_PAGE_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers[ALLOW_ORIGIN] == "*"
    assert "POST" in response.headers[ALLOW_METHODS]
    assert "content-type" in response.headers[ALLOW_HEADERS].lower()


def test_a_cross_origin_get_carries_the_allow_origin_header(browser: TestClient) -> None:
    response = browser.get("/v1/site", headers={"Origin": STATIC_PAGE_ORIGIN})

    assert response.status_code == 200, response.text
    assert response.headers.get(ALLOW_ORIGIN) == "*", (
        "without this header the browser discards the body and the frontend shows "
        "the OFFLINE banner although the service answered"
    )


def test_a_cross_origin_post_to_windows_succeeds(
    browser: TestClient, sso_request: dict[str, Any]
) -> None:
    """The call the page makes on load: POST /v1/windows from another origin."""
    response = browser.post(
        "/v1/windows", json=sso_request, headers={"Origin": STATIC_PAGE_ORIGIN}
    )

    assert response.status_code == 200, response.text
    assert response.headers.get(ALLOW_ORIGIN) == "*"
    body = response.json()
    assert isinstance(body["windows"], list)
    assert body["engine_version"]


def test_an_unrelated_origin_is_still_answered_under_the_wildcard(
    browser: TestClient,
) -> None:
    """The wildcard is the configured policy, so no origin is refused."""
    response = browser.get("/v1/health", headers={"Origin": UNRELATED_ORIGIN})

    assert response.status_code == 200, response.text
    assert response.headers.get(ALLOW_ORIGIN) == "*"


def test_same_origin_responses_are_unchanged(browser: TestClient) -> None:
    """A request with no Origin header is not cross-origin and must not change.

    This is the one test that passes with and without the middleware: the layer adds
    headers to cross-origin answers and leaves every other answer as it was.
    """
    same_origin = browser.get("/v1/health")
    cross_origin = browser.get("/v1/health", headers={"Origin": STATIC_PAGE_ORIGIN})

    assert same_origin.status_code == 200, same_origin.text
    assert same_origin.json()["status"] == "ok"
    assert ALLOW_ORIGIN not in same_origin.headers
    assert same_origin.json() == cross_origin.json(), "the layer changes headers, never a body"


def test_the_openapi_document_is_still_served(browser: TestClient) -> None:
    response = browser.get("/v1/openapi.json", headers={"Origin": STATIC_PAGE_ORIGIN})

    assert response.status_code == 200, response.text
    document = response.json()
    assert document["openapi"]
    assert "/v1/windows" in document["paths"]
    assert response.headers.get(ALLOW_ORIGIN) == "*"
