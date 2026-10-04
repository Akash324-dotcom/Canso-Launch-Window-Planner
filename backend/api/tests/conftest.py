"""Shared fixtures for the backend API tests, tasks A1 to A3 of issue #4.

Which layers a test sees. The suite was written with two paths in mind (see the
module docstrings of ``test_windows.py`` and ``test_weather.py``): the offline path,
exercised directly, and the seam, exercised through a stand-in module placed in
``sys.modules``. Both assume that ``backend.engine`` and ``backend.weather`` are not
importable unless a test puts them there. Since ENGINE and WEATHER landed that is no
longer true of the repository, so the ``layers`` fixture below restores it for every
test: the two real modules are hidden from the import system, a stand-in installed
by a test still wins, and a test marked ``live_layers`` gets the real modules.

A test marked ``live_layers`` runs the real weather module with
``LAUNCHWIN_WEATHER_OFFLINE=1`` and an empty private cache, so it answers from the
committed forecast snapshot and the committed climatology and never from the network.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]


LIVE_LAYERS = ("backend.engine", "backend.weather")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_layers: run against the real backend.engine and backend.weather instead of the offline path",
    )


@pytest.fixture(autouse=True)
def layers(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Hide the real engine and weather modules unless the test asks for them."""
    monkeypatch.setenv("LAUNCHWIN_WEATHER_OFFLINE", "1")
    if request.node.get_closest_marker("live_layers") is None:
        for name in LIVE_LAYERS:
            # None in sys.modules makes importlib.import_module raise ImportError,
            # which is exactly what the seams treat as "this layer has not landed".
            monkeypatch.setitem(sys.modules, name, None)
        return

    from backend.weather import fetch, hindcast, service

    monkeypatch.setattr(fetch, "CACHE_DIR", tmp_path / "weather_cache")
    monkeypatch.setattr(hindcast, "CACHE_DIR", tmp_path / "hindcast_cache")
    fetch.clear_memo()
    service.clear_memo()


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