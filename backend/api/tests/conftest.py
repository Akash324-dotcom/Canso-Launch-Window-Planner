"""Shared fixtures for the backend API tests, tasks A1 to A3 of issue #4."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]


@pytest.fixture(scope="session")
def settings() -> Settings:
    """The service settings as loaded from backend/api/data."""
    return Settings.load()


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient over a fresh app instance, so no state leaks between tests."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def sso_request() -> dict[str, Any]:
    """A well formed SSO request, the canonical demo case."""
    return {
        "target": {"type": "SSO", "h_t_km": 674.0},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": True,
    }


@pytest.fixture()
def leo_request() -> dict[str, Any]:
    """The advertised LEO 45.1 deg case, unreachable by direct ascent from Canso."""
    return {
        "target": {"type": "LEO"},
        "site": "canso",
        "date_range": {"start": "2026-10-05", "end": "2026-10-15"},
        "vehicle_profile_id": "cyclone4m",
        "include_weather": False,
    }