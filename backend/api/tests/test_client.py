"""Task A8: the public Python client of spec IV.9.

The acceptance tests of the A8 task, one section each:

* the three lines of spec IV.9 return a DataFrame, exercised against a FastAPI
  ``TestClient`` so that the request the client builds is the request the service
  actually receives;
* the client works against the fixtures only application, which is the demo path of
  spec V.5 and the state the service is in until ENGINE lands;
* a 4xx or a 5xx raises ``LaunchwinError`` carrying what the service said, while the
  three domain outcomes of spec IV.7 rule 1 return an empty frame with the response
  intact and raise nothing;
* the two read surfaces return their documents, and the ephemeris returns points;
* ``import launchwin`` and a call work from a directory outside the repository.

Two of those five depend on the distribution being installed in the virtual
environment, which this workspace cannot do: the environment has no ``pip`` and no
``setuptools`` and no network, so ``pip install -e .`` cannot be run here. The two
subprocess tests therefore skip, with a reason that says so, and what they assert is
additionally pinned statically: the packaging mapping in ``pyproject.toml``, the hard
``pandas`` dependency, and the fact that the client module imports nothing from the
repository. Those three assertions are what a reviewer can check without installing
anything, and they are the parts of the installation contract that a change to this
workflow's own files could break.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Callable

import httpx
import pandas
import pytest
from fastapi.testclient import TestClient

import launchwin
from backend.api import stubs
from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.schemas import load_schemas

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]
CLIENT_DIR = REPO_ROOT / "backend" / "client"
CLIENT_MODULE = CLIENT_DIR / "launchwin.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

DEMO_DATES = ("2026-10-04", "2027-01-01")
PUBLIC_FUNCTIONS = ("windows", "weather", "skill", "site", "ephemeris", "citation")

#: Held at module scope so the directory outlives collection and is removed at exit.
PROBE_DIRECTORY = tempfile.TemporaryDirectory(prefix="launchwin-outside-repo-")
PROBE_DIR = Path(PROBE_DIRECTORY.name)


def _run_in_a_directory_outside_the_repository(statement: str) -> subprocess.CompletedProcess[str]:
    """Run one statement in the interpreter of the virtual environment, elsewhere."""
    return subprocess.run(
        [str(VENV_PYTHON), "-c", statement],
        cwd=PROBE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


IMPORT_PROBE = "import launchwin; print(launchwin.__file__)"
IMPORT_PROBE_RESULT = _run_in_a_directory_outside_the_repository(IMPORT_PROBE)
LAUNCHWIN_INSTALLED = IMPORT_PROBE_RESULT.returncode == 0
NOT_INSTALLED = (
    "launchwin is not importable in the virtual environment: the interpreter at "
    f"{VENV_PYTHON} cannot import it from {PROBE_DIR}, exiting "
    f"{IMPORT_PROBE_RESULT.returncode} with {IMPORT_PROBE_RESULT.stderr.strip()!r}"
    "; run pip install -e . in that environment first"
)


class RecordingTestClient(TestClient):
    """A ``TestClient`` that remembers what it was asked to do.

    It exists for the branch in which the module opens and closes a transport of its
    own, which no caller ever passes in and which would otherwise be the only part of
    the client no assertion could observe.
    """

    def __init__(self, app: Any) -> None:
        self.calls: list[tuple[str, str]] = []
        super().__init__(app)

    def request(self, method: str, url: Any, **kwargs: Any) -> httpx.Response:
        self.calls.append((method, str(url)))
        return super().request(method, url, **kwargs)


def transport_recorder(
    app: Any,
) -> tuple[Callable[..., RecordingTestClient], list[RecordingTestClient], list[dict[str, Any]]]:
    """A stand in for ``httpx.Client`` that routes to ``app`` and records its arguments."""
    created: list[RecordingTestClient] = []
    asked: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> RecordingTestClient:
        asked.append(kwargs)
        client = RecordingTestClient(app)
        created.append(client)
        return client

    return factory, created, asked


def module_imports(path: Path) -> set[str]:
    """Every module the file imports, read from the parse tree rather than the text.

    The text of a module contains its own name in examples and in prose, so a regular
    expression would find imports that are not there and miss the ones that are.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def contract_window_columns() -> tuple[str, ...]:
    """The expected column order, read from the frozen schema rather than restated."""
    schemas, _ = load_schemas()
    definitions = schemas["windows_response"]["$defs"]
    flattened = {
        "p_success_components": {
            name: column for column, name in launchwin.COMPONENT_COLUMNS.items()
        },
        "screens": {name: column for column, name in launchwin.SCREEN_COLUMNS.items()},
    }
    columns: list[str] = []
    for field in definitions["window"]["properties"]:
        if field in flattened:
            columns.extend(
                flattened[field][name] for name in definitions[field]["properties"]
            )
        else:
            columns.append(field)
    return tuple(columns)


def pyproject() -> dict[str, Any]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_configured_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default base URL in force for every test here.

    A ``LAUNCHWIN_URL`` in the shell that started the suite must not steer a test: the
    tests assert the documented default, and the ones that pass a ``TestClient`` need
    the request to land on the application rather than on a configured host.
    """
    monkeypatch.delenv(launchwin.BASE_URL_ENV, raising=False)


def requirement_name(requirement: str) -> str:
    return re.split(r"[^\w.-]", requirement, maxsplit=1)[0]


# --------------------------------------------------------------------------
# The surface spec IV.9 names
# --------------------------------------------------------------------------


def test_the_package_and_the_module_are_one_implementation() -> None:
    """``backend.client.launchwin`` and ``launchwin`` are one file, imported twice."""
    import backend.client as client_package

    assert sorted(client_package.__all__) == sorted(launchwin.__all__)
    assert client_package.launchwin.__file__ == launchwin.__file__
    assert Path(launchwin.__file__).resolve() == CLIENT_MODULE.resolve()


def test_every_public_function_takes_a_base_url_and_a_client() -> None:
    for name in PUBLIC_FUNCTIONS:
        parameters = inspect.signature(getattr(launchwin, name)).parameters
        assert "base_url" in parameters, name
        assert "client" in parameters, name
        assert parameters["base_url"].default is None, name
        assert parameters["client"].default is None, name


def test_the_documented_defaults_are_the_ones_the_specification_names() -> None:
    windows_signature = inspect.signature(launchwin.windows)
    assert windows_signature.parameters["site"].default == "canso"
    assert windows_signature.parameters["vehicle"].default == "cyclone4m"
    assert windows_signature.parameters["include_weather"].default is True
    assert windows_signature.parameters["dates"].default is inspect.Parameter.empty
    assert inspect.signature(launchwin.weather).parameters["site"].default == "canso"
    assert inspect.signature(launchwin.skill).parameters["lead_max"].default == 10
    assert inspect.signature(launchwin.ephemeris).parameters["step_s"].default == 300


def test_the_base_url_default_is_the_environment_then_localhost() -> None:
    assert launchwin.BASE_URL_ENV == "LAUNCHWIN_URL"
    assert launchwin.DEFAULT_BASE_URL == "http://localhost:8000/v1"


# --------------------------------------------------------------------------
# The three lines of spec IV.9, against the application itself
# --------------------------------------------------------------------------


def test_the_three_lines_of_spec_iv_9_return_a_data_frame(client: TestClient) -> None:
    """The acceptance test of the A8 task, verbatim apart from the injected transport.

    ``client`` is the only addition, and it is how the specification's three lines are
    exercised without a server listening: it is the same request the module would send
    over the network, built by the same code.
    """
    frame = launchwin.windows(
        target="SSO", site="canso", dates=("2026-10-04", "2027-01-01"), client=client
    )

    assert isinstance(frame, pandas.DataFrame)
    assert len(frame) == 3
    assert list(frame.columns) == list(launchwin.WINDOW_COLUMNS)


def test_one_row_per_window_of_the_response(client: TestClient) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)
    response = frame.attrs["response"]

    assert len(frame) == len(response["windows"])


def test_the_columns_are_the_frozen_window_fields_with_two_objects_flattened(
    client: TestClient,
) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)

    assert launchwin.WINDOW_COLUMNS == contract_window_columns()


def test_the_whole_response_is_available_in_attrs(client: TestClient) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)
    response = frame.attrs["response"]
    direct = client.post(
        "/v1/windows",
        json={
            "target": {"type": "SSO"},
            "site": "canso",
            "date_range": {"start": DEMO_DATES[0], "end": DEMO_DATES[1]},
            "vehicle_profile_id": "cyclone4m",
            "include_weather": True,
        },
    ).json()

    assert response == direct
    assert set(response) == {
        "reachable",
        "plane_change_dv_ms",
        "sso_consistency_warning",
        "windows",
        "constants_block",
        "provenance_block",
        "engine_version",
        "computation_ms",
    }


def test_every_field_of_a_row_survives_the_flattening(client: TestClient) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)

    for row, window in zip(frame.to_dict("records"), frame.attrs["response"]["windows"]):
        assert row["t_liftoff_utc"] == window["t_liftoff_utc"]
        assert row["p_success"] == window["p_success"]
        assert row["p_weather"] == window["p_success_components"]["weather"]
        assert row["p_range"] == window["p_success_components"]["range"]
        assert row["p_conjunction"] == window["p_success_components"]["conjunction"]
        assert row["screen_hazard"] == window["screens"]["hazard"]
        assert row["screen_conjunction"] == window["screens"]["conjunction"]
        assert row["screen_notam"] == window["screens"]["notam"]
        assert set(row) == set(launchwin.WINDOW_COLUMNS)


def test_the_two_conjunction_fields_of_a_row_do_not_collide() -> None:
    """Both objects of a spec IV.1 row hold a ``conjunction``, so the names differ."""
    assert "conjunction" in launchwin.COMPONENT_COLUMNS.values()
    assert "conjunction" in launchwin.SCREEN_COLUMNS.values()
    assert not set(launchwin.COMPONENT_COLUMNS) & set(launchwin.SCREEN_COLUMNS)
    assert len(launchwin.WINDOW_COLUMNS) == len(set(launchwin.WINDOW_COLUMNS))


def test_a_custom_target_object_reaches_the_service_intact(client: TestClient) -> None:
    """The two numbers of a CUSTOM orbit are the request's, so the answer changes."""
    matched = launchwin.windows(
        target={"type": "CUSTOM", "h_t_km": 674.0, "i_t_deg": 98.0},
        dates=DEMO_DATES,
        client=client,
    )
    unmatched = launchwin.windows(
        target={"type": "CUSTOM", "h_t_km": 674.0, "i_t_deg": 97.0},
        dates=DEMO_DATES,
        client=client,
    )
    unreachable = launchwin.windows(
        target={"type": "CUSTOM", "h_t_km": 500.0, "i_t_deg": 40.0},
        dates=DEMO_DATES,
        client=client,
    )

    assert len(matched) == 3
    assert len(unmatched) == 0
    assert unmatched.attrs["response"]["reachable"] is True
    assert unreachable.attrs["response"]["reachable"] is False
    assert unreachable.attrs["response"]["plane_change_dv_ms"] > 0.0


def test_a_target_name_is_upper_cased_so_the_request_is_the_same_one(client: TestClient) -> None:
    upper = launchwin.windows(target="SSO", dates=DEMO_DATES, client=client)
    lower = launchwin.windows(target="sso", dates=DEMO_DATES, client=client)

    assert (
        upper.attrs["response"]["constants_block"]["citation_id"]
        == lower.attrs["response"]["constants_block"]["citation_id"]
    )


def test_a_date_mapping_and_a_pair_build_the_same_request(client: TestClient) -> None:
    as_pair = launchwin.windows(target="SSO", dates=DEMO_DATES, client=client)
    as_mapping = launchwin.windows(
        target="SSO", dates={"start": DEMO_DATES[0], "end": DEMO_DATES[1]}, client=client
    )

    assert as_pair.attrs["response"] == as_mapping.attrs["response"]


def test_include_weather_false_reaches_the_service(client: TestClient) -> None:
    """The four weather fields are the ones the service changes for this request."""
    frame = launchwin.windows(
        target="SSO", dates=DEMO_DATES, include_weather=False, client=client
    )

    assert set(frame["horizon_label"]) == {"CLIMATOLOGY"}
    assert frame["forecast_issue_time"].isna().all()
    assert frame["p_weather"].tolist() == [1.0, 1.0, 1.0]


@pytest.mark.parametrize(
    "dates",
    [("2026-10-05",), ("2026-10-05", "2026-10-10", "2026-10-15"), "2026-10-05"],
)
def test_dates_that_are_not_a_pair_are_refused_before_any_request(
    client: TestClient, dates: Any
) -> None:
    with pytest.raises(ValueError):
        launchwin.windows(target="SSO", dates=dates, client=client)


def test_a_target_without_a_type_is_refused_before_any_request(client: TestClient) -> None:
    with pytest.raises(ValueError):
        launchwin.windows(target="", dates=DEMO_DATES, client=client)
    with pytest.raises(ValueError):
        launchwin.windows(target={"h_t_km": 674.0}, dates=DEMO_DATES, client=client)


# --------------------------------------------------------------------------
# The fixtures only application, the demo path of spec V.5
# --------------------------------------------------------------------------


def test_the_client_works_against_the_fixtures_only_app(client: TestClient) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)
    response = frame.attrs["response"]

    assert response["engine_version"] == stubs.STUB_ENGINE_VERSION
    assert "backend/fixtures/windows.json" in response["provenance_block"]["source_files"]
    assert "backend/fixtures/weather.json" in response["provenance_block"]["source_files"]
    assert len(frame) == 3


def test_the_rows_are_the_recorded_offline_rows_unchanged(
    client: TestClient, settings: Settings
) -> None:
    document = json.loads(settings.fixture_path("windows").read_text(encoding="utf-8"))
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)

    served = frame.attrs["response"]["windows"]
    for row, window in zip(frame.to_dict("records"), served):
        assert row["t_liftoff_utc"] == window["t_liftoff_utc"]
        assert row["p_success"] == pytest.approx(
            document["windows"][0]["p_success_components"]["weather"]
            * row["p_range"]
            * row["p_conjunction"]
        )
    assert [window["t_liftoff_utc"] for window in served] == [
        window["t_liftoff_utc"] for window in document["windows"]
    ]


# --------------------------------------------------------------------------
# Domain outcomes are answers, never exceptions, spec IV.7 rule 1
# --------------------------------------------------------------------------


def test_no_window_in_range_returns_an_empty_frame_and_the_response(
    client: TestClient,
) -> None:
    frame = launchwin.windows(target="POLAR", dates=DEMO_DATES, client=client)

    assert len(frame) == 0
    assert list(frame.columns) == list(launchwin.WINDOW_COLUMNS)
    assert frame.attrs["response"]["reachable"] is True
    assert frame.attrs["response"]["windows"] == []


def test_an_unreachable_target_returns_an_empty_frame_with_the_penalty(
    client: TestClient,
) -> None:
    frame = launchwin.windows(target="LEO", dates=DEMO_DATES, client=client)

    assert len(frame) == 0
    assert frame.attrs["response"]["reachable"] is False
    assert frame.attrs["response"]["plane_change_dv_ms"] == pytest.approx(26.8, abs=1.0)
    assert frame.attrs["response"]["constants_block"]["citation_id"]


def test_a_fired_constraint_is_a_row_and_not_an_exception(
    client: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = json.loads(settings.fixture_path("windows").read_text(encoding="utf-8"))
    document["windows"][0]["constraint_fired"] = "hazard_area"
    document["windows"][0]["screens"]["hazard"] = "fail"
    monkeypatch.setattr(stubs, "load_windows_document", lambda resolved: document)

    frame = launchwin.windows(target="SSO", dates=DEMO_DATES, client=client)

    assert frame["constraint_fired"].iloc[0] == "hazard_area"
    assert frame["constraint_fired"].iloc[1:].isna().all()
    assert frame["screen_hazard"].tolist() == ["fail", "pass", "pass"]


# --------------------------------------------------------------------------
# The four conditions of spec IV.7 rule 2 raise
# --------------------------------------------------------------------------


def test_an_unknown_run_id_raises_with_what_the_service_said(client: TestClient) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.citation("run_20261004_000000000000", client=client)

    failure = caught.value
    assert failure.status_code == 404
    assert "was not found" in str(failure.detail)
    assert failure.payload["resource_kind"] == "run"
    assert failure.url.endswith("/v1/citation")


def test_an_unknown_orbit_id_raises_with_what_the_service_said(client: TestClient) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.ephemeris(
            "no_such_orbit", "2026-10-05T00:00:00Z", "2026-10-05T01:00:00Z", client=client
        )

    failure = caught.value
    assert failure.status_code == 404
    assert failure.detail == "unknown orbit id 'no_such_orbit'"


def test_a_malformed_request_raises_422_with_the_schema_violations(
    client: TestClient,
) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.windows(target="SSO", dates=("05-10-2026", "2026-10-15"), client=client)

    failure = caught.value
    assert failure.status_code == 422
    assert failure.payload["schema_name"] == "windows_request"
    assert failure.payload["violations"]
    assert failure.payload["violations"][0].startswith("/date_range/start")


def test_an_unavailable_upstream_raises_503_naming_the_offline_document(
    client: TestClient,
) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.weather("2026-11-06", client=client)

    failure = caught.value
    assert failure.status_code == 503
    assert int(failure.retry_after_s) > 0
    assert failure.payload["fixture_path_active"] is True
    assert failure.payload["offline_fixture_path"] == "backend/fixtures/weather.json"


def test_a_spent_budget_raises_429_carrying_retry_after(
    settings: Settings, client_for: Callable[[Settings], TestClient]
) -> None:
    limited = settings.with_service_overrides("rate_limit", reads_per_window=1)
    with client_for(limited) as service:
        assert launchwin.site(client=service)["name"] == "canso"
        with pytest.raises(launchwin.LaunchwinError) as caught:
            launchwin.site(client=service)

    failure = caught.value
    assert failure.status_code == 429
    assert int(failure.retry_after_s) > 0
    assert failure.payload["error"] == "rate_limit_exceeded"


def test_the_message_states_the_method_the_url_the_status_and_the_detail(
    client: TestClient,
) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.citation("run_20261004_000000000000", client=client)

    message = str(caught.value)
    assert message.startswith("GET http://localhost:8000/v1/citation returned HTTP 404: ")
    assert "was not found" in message
    assert caught.value.method == "GET"


def test_a_request_that_never_completes_raises_without_a_status_code() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.Client(transport=httpx.MockTransport(refuse))
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.site(client=transport)

    failure = caught.value
    assert failure.status_code is None
    assert failure.retry_after_s is None
    assert "ConnectError" in str(failure)


# --------------------------------------------------------------------------
# The read surfaces beside the window call
# --------------------------------------------------------------------------


def test_weather_returns_the_spec_iv_3_document(client: TestClient) -> None:
    document = launchwin.weather("2026-10-06", client=client)

    assert document["date"] == "2026-10-06"
    assert document["site"] == "canso"
    assert 0.0 <= document["p_launch"] <= 1.0
    assert document["horizon_label"] in ("FORECAST", "CLIMATOLOGY")
    assert document["source"] == "snapshot_cache"
    assert document["components"]


def test_weather_takes_a_site(client: TestClient) -> None:
    assert launchwin.weather("2026-10-06", site="canso", client=client)["site"] == "canso"


def test_skill_returns_the_spec_iv_4_document_truncated_to_lead_max(
    client: TestClient,
) -> None:
    recorded = json.loads(Settings.load().fixture_path("skill").read_text(encoding="utf-8"))
    period = recorded["period"]
    recorded_leads = [row["lead_time_days"] for row in recorded["skill_series"]]

    full = launchwin.skill(period["start"], period["end"], client=client)
    short = launchwin.skill(period["start"], period["end"], lead_max=1, client=client)

    assert full["period"] == period
    assert full["verification_source"] == "era5"
    assert [row["lead_time_days"] for row in full["skill_series"]] == recorded_leads
    assert len(recorded_leads) > 1, "the record must hold more than one lead for the truncation to show"
    assert [row["lead_time_days"] for row in short["skill_series"]] == [1]
    assert full["reliability_bins"] and full["roc_points"]
    assert full["constants_block"]["citation_id"]


def test_site_returns_the_spec_iv_5_document_for_the_configured_site(
    client: TestClient,
) -> None:
    document = launchwin.site(client=client)

    assert document["name"] == "canso"
    assert document["corridor"]["A_min_deg"] is not None
    assert document["corridor"]["source"]
    assert document["car_references"] == ["602.43", "602.44"]


def test_ephemeris_returns_one_row_per_point_with_the_document_in_attrs(
    client: TestClient,
) -> None:
    frame = launchwin.ephemeris(
        "sso981", "2026-10-05T00:00:00Z", "2026-10-05T01:00:00Z", client=client
    )
    response = frame.attrs["response"]

    assert list(frame.columns) == list(launchwin.POINT_COLUMNS)
    assert len(frame) == len(response["points"]) == 13
    assert response["frame"] == "ECEF"
    assert response["ground_track_valid"] is True
    assert frame["alt_km"].unique().tolist() == [674.0]
    assert frame["t_utc"].iloc[0] == "2026-10-05T00:00:00Z"


def test_ephemeris_honours_the_requested_step(client: TestClient) -> None:
    coarse = launchwin.ephemeris(
        "sso981", "2026-10-05T00:00:00Z", "2026-10-05T01:00:00Z", step_s=900, client=client
    )

    assert len(coarse) == 5
    assert coarse.attrs["response"]["points"][1]["t_utc"] == "2026-10-05T00:15:00Z"


def test_ephemeris_beyond_the_horizon_reports_an_invalid_ground_track(
    client: TestClient,
) -> None:
    frame = launchwin.ephemeris(
        "sso981", "2026-10-05T00:00:00Z", "2026-10-09T12:00:00Z", step_s=7200, client=client
    )

    assert frame.attrs["response"]["ground_track_valid"] is False
    assert len(frame) == 55


def test_citation_reproduces_the_run_a_window_response_named(client: TestClient) -> None:
    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES, client=client)
    citation_id = frame.attrs["response"]["constants_block"]["citation_id"]

    document = launchwin.citation(citation_id, client=client)

    assert document["citation_id"] == citation_id
    assert document["criteria_version"] == frame.attrs["response"]["provenance_block"][
        "criteria_version"
    ]
    assert document["constants"]["GM"] == frame.attrs["response"]["constants_block"]["GM"]
    assert document["engine_version"] == stubs.STUB_ENGINE_VERSION
    assert document["source_files"]
    assert document["items"]


# --------------------------------------------------------------------------
# The base URL and the transport
# --------------------------------------------------------------------------


def test_the_base_url_defaults_to_localhost_8000_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(launchwin.BASE_URL_ENV, raising=False)

    assert launchwin.resolve_base_url() == "http://localhost:8000/v1"
    assert launchwin.resolve_base_url(None) == "http://localhost:8000/v1"


def test_the_environment_variable_is_read_when_no_argument_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(launchwin.BASE_URL_ENV, "https://engine.example.org/v1")

    assert launchwin.resolve_base_url() == "https://engine.example.org/v1"


def test_an_argument_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(launchwin.BASE_URL_ENV, "https://ignored.example.org/v1")

    assert launchwin.resolve_base_url("https://engine.example.org/v1") == (
        "https://engine.example.org/v1"
    )


def test_a_trailing_slash_does_not_produce_a_double_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(launchwin.BASE_URL_ENV, raising=False)

    assert launchwin.resolve_base_url("http://testserver/v1/") == "http://testserver/v1"
    assert launchwin.resolve_base_url("  http://testserver/v1  ") == "http://testserver/v1"


def test_an_empty_base_url_is_refused_rather_than_defaulted() -> None:
    with pytest.raises(ValueError):
        launchwin.resolve_base_url("")
    with pytest.raises(ValueError):
        launchwin.resolve_base_url("   ")


def test_an_empty_environment_variable_reads_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(launchwin.BASE_URL_ENV, "")

    assert launchwin.resolve_base_url() == launchwin.DEFAULT_BASE_URL


def test_a_base_url_argument_reaches_the_request(client: TestClient) -> None:
    with pytest.raises(launchwin.LaunchwinError) as caught:
        launchwin.citation(
            "run_20261004_000000000000", base_url="http://elsewhere.invalid/v1", client=client
        )

    assert caught.value.url == "http://elsewhere.invalid/v1/citation"


def test_the_module_opens_a_transport_of_its_own_and_closes_it(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, created, asked = transport_recorder(create_app(settings))
    monkeypatch.setattr(launchwin.httpx, "Client", factory)

    frame = launchwin.windows(target="SSO", site="canso", dates=DEMO_DATES)

    assert len(frame) == 3
    assert asked == [{"timeout": launchwin.DEFAULT_TIMEOUT_S}]
    assert [client.calls for client in created] == [
        [("POST", "http://localhost:8000/v1/windows")]
    ]
    assert [client.is_closed for client in created] == [True]


def test_the_transport_of_the_module_carries_the_base_url_it_resolved(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default base URL reaches the request URL, with no trailing slash doubled."""
    factory, created, _asked = transport_recorder(create_app(settings))
    monkeypatch.setattr(launchwin.httpx, "Client", factory)
    monkeypatch.setenv(launchwin.BASE_URL_ENV, "https://engine.example.org/v1/")

    launchwin.site()

    assert created[0].calls == [("GET", "https://engine.example.org/v1/site")]
    assert created[0].is_closed is True


# --------------------------------------------------------------------------
# The distribution
# --------------------------------------------------------------------------


def test_the_repository_layout_is_mapped_onto_the_launchwin_module() -> None:
    """What ``pip install -e .`` needs, asserted without installing anything."""
    configuration = pyproject()

    assert configuration["tool"]["setuptools"]["py-modules"] == ["launchwin"]
    assert configuration["tool"]["setuptools"]["package-dir"] == {
        "launchwin": "backend/client"
    }
    assert CLIENT_MODULE.is_file()
    assert CLIENT_DIR.joinpath("__init__.py").is_file()


def test_the_backend_packages_are_still_discovered() -> None:
    configuration = pyproject()

    assert configuration["tool"]["setuptools"]["packages"]["find"]["include"] == ["backend*"]


def test_pandas_is_a_declared_hard_dependency() -> None:
    """The A8 task allows a declared hard dependency instead of a lazy import."""
    dependencies = pyproject()["project"]["dependencies"]

    assert "pandas" in [requirement_name(item) for item in dependencies]
    assert "pandas" not in pyproject()["project"]["optional-dependencies"]["dev"]


def test_the_client_module_imports_nothing_from_the_repository() -> None:
    """What makes an installed copy work outside the repository."""
    imported = module_imports(CLIENT_MODULE)

    assert imported == {
        "__future__",
        "os",
        "collections.abc",
        "typing",
        "urllib.parse",
        "httpx",
        "pandas",
    }
    assert "backend" not in imported


def test_the_test_suite_can_reach_the_client_without_it_being_installed() -> None:
    """Why ``pythonpath`` names the client directory in the pytest configuration."""
    assert pyproject()["tool"]["pytest"]["ini_options"]["pythonpath"] == ["backend/client"]
    assert launchwin.__file__ == str(CLIENT_MODULE)


@pytest.mark.skipif(not LAUNCHWIN_INSTALLED, reason=NOT_INSTALLED)
def test_launchwin_imports_from_a_directory_outside_the_repository() -> None:
    result = _run_in_a_directory_outside_the_repository(IMPORT_PROBE)

    assert result.returncode == 0, result.stderr
    module_path = Path(result.stdout.strip())
    # Installed, ``launchwin`` is the package mapped onto backend/client, whose
    # __init__ re-exports backend/client/launchwin.py; both resolve to that directory.
    assert module_path.parent == CLIENT_MODULE.parent
    assert module_path.is_file()
    assert PROBE_DIR not in module_path.parents
    assert module_path.is_relative_to(REPO_ROOT) or "site-packages" in module_path.parts


_OUTSIDE_CALL = (
    "import launchwin",
    "from fastapi.testclient import TestClient",
    "from backend.api.app import create_app",
    "from backend.api.config import Settings",
    "settings = Settings.load().with_runs_dir(" + repr(str(PROBE_DIR / "runs")) + ")",
    "with TestClient(create_app(settings)) as service:",
    "    frame = launchwin.windows(",
    '        target="SSO", site="canso", dates=("2026-10-04", "2027-01-01"),',
    "        client=service,",
    "    )",
    'summary = "rows=%d engine=%s" % (len(frame), frame.attrs["response"]["engine_version"])',
    "print(summary)",
)


@pytest.mark.skipif(not LAUNCHWIN_INSTALLED, reason=NOT_INSTALLED)
def test_launchwin_imports_and_calls_from_a_directory_outside_the_repository() -> None:
    statement = "\n".join(
        [
            "import sys",
            # The offline path, as in the rest of this suite (see conftest.layers).
            'sys.modules["backend.engine"] = None',
            'sys.modules["backend.weather"] = None',
            *_OUTSIDE_CALL,
        ]
    )

    result = _run_in_a_directory_outside_the_repository(statement)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "rows=3 engine=stub"


@pytest.mark.skipif(not LAUNCHWIN_INSTALLED, reason=NOT_INSTALLED)
def test_launchwin_calls_the_live_engine_from_a_directory_outside_the_repository() -> None:
    """The same call against the real engine and the real weather layer, read offline."""
    from backend import engine

    runs_directory = str(PROBE_DIR / "runs-live")
    statement = "\n".join(
        [
            "import os",
            'os.environ["LAUNCHWIN_WEATHER_OFFLINE"] = "1"',
            *[line.replace(repr(str(PROBE_DIR / "runs")), repr(runs_directory)) for line in _OUTSIDE_CALL],
            'rows = frame.attrs["response"]["windows"]',
            'print("weather=%s" % sorted({row["horizon_label"] for row in rows}))',
            'print("sources=%s" % frame.attrs["response"]["provenance_block"]["source_files"])',
        ]
    )

    result = _run_in_a_directory_outside_the_repository(statement)

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    rows, version = re.fullmatch(r"rows=(\d+) engine=(\S+)", lines[0]).groups()
    assert version == engine.ENGINE_VERSION
    assert int(rows) > 3, "a three month range holds more crossings than the three recorded rows"
    assert "backend/fixtures/windows.json" not in lines[2]