"""Shared fixtures for the backend API tests, tasks A1 to A3 of issue #4."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]


@pytest.fixture(scope="session")
def runs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Directory the run store writes to, outside the working tree.

    The configured location is ``backend/api/data/runs`` and the suite exercises it
    in ``test_citation.py``; keeping the default clients off it means a test run
    leaves nothing behind in the repository.
    """
    return tmp_path_factory.mktemp("runs")


@pytest.fixture(scope="session")
def settings(runs_dir: Path) -> Settings:
    """The service settings as loaded from backend/api/data."""
    return Settings.load().with_runs_dir(runs_dir)


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    """A TestClient over a fresh app instance, so no state leaks between tests."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def client_for() -> Callable[[Settings], Any]:
    """Build a client over an app configured differently from the default one.

    The caches, the rate limiter and the run store all hang off the application, so
    a test that wants the shipped limits, a short TTL or a different offline
    document needs its own application rather than a mutated global.
    """

    @contextmanager
    def build(overrides: Settings) -> Iterator[TestClient]:
        with TestClient(create_app(overrides)) as test_client:
            yield test_client

    return build


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