"""Shared fixtures for the weather tests.

Tests never touch the network. Every test starts in offline mode with a transport that refuses any request and
with the disk cache redirected to a temporary directory. A test that exercises the live path installs the
mocked Upstream below, which replays committed fixtures.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class Upstream:
    """A mocked Open-Meteo: serves committed fixtures, counts calls, and can be told to fail.

    ``down`` names models whose data endpoint answers 503. ``meta`` overrides a run-metadata response; None
    makes that metadata endpoint answer 404. ``payloads`` overrides a data response.
    """

    def __init__(self, down=(), meta=None, payloads=None):
        self.down = set(down)
        self.meta = {"ncep_gfs013": load_fixture("meta_ncep_gfs013.json"),
                     "cmc_gem_gdps": load_fixture("meta_cmc_gem_gdps.json"),
                     "ecmwf_ifs025_ensemble": load_fixture("meta_ecmwf_ifs025_ensemble.json"),
                     "ncep_gefs05": load_fixture("meta_ncep_gefs05.json")}
        if meta is not None:
            self.meta.update(meta)
        self.payloads = {"gfs_seamless": load_fixture("open_meteo_forecast_canso.json"),
                         "gem_global": load_fixture("open_meteo_gdps_canso.json"),
                         "ecmwf_ifs025": load_fixture("open_meteo_ensemble_canso.json"),
                         "gfs05": load_fixture("open_meteo_gefs_ensemble_canso.json")}
        if payloads is not None:
            self.payloads.update(payloads)
        self.data_calls: list[str] = []
        self.meta_calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/static/meta.json"):
            model = path.split("/")[2]
            self.meta_calls.append(model)
            if self.meta.get(model) is None:
                return httpx.Response(404, json={"error": True})
            return httpx.Response(200, json=self.meta[model])
        model = request.url.params["models"]
        self.data_calls.append(model)
        if model in self.down:
            return httpx.Response(503, json={"error": True, "reason": "upstream outage"})
        return httpx.Response(200, json=self.payloads[model])

    @property
    def calls(self) -> int:
        return len(self.data_calls) + len(self.meta_calls)

    def install(self) -> "Upstream":
        """Route every request to this mock and leave offline mode, so the live path is exercised."""
        from backend.weather import fetch

        os.environ.pop(fetch.OFFLINE_ENV, None)
        fetch.set_transport(httpx.MockTransport(self))
        return self


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"test attempted a network call to {request.url}")


@pytest.fixture(autouse=True)
def isolated_weather(tmp_path, monkeypatch):
    """Offline mode, a refusing transport, a private cache directory and clean memos for every test."""
    from backend.weather import fetch, service

    monkeypatch.setenv(fetch.OFFLINE_ENV, "1")
    monkeypatch.setattr(fetch, "CACHE_DIR", tmp_path / "cache")
    fetch.set_transport(httpx.MockTransport(_refuse))
    fetch.clear_memo()
    service.clear_memo()
    yield
    fetch.set_transport(None)
    fetch.clear_memo()
    service.clear_memo()
