"""G5 integration harness (issue #4 task A10, run by issue #6 section 3).

Runs the whole /v1 surface in process through FastAPI's TestClient and checks:
(1) fixtures validate against the frozen schemas, (2) the app boots, (3) SSO,
POLAR and LEO requests are answered, (4) LEO 45.1 is unreachable with a
plane-change penalty, (5) site, weather and skill respond, (6) the run's
citation resolves, (7) identical requests give identical results.

Exit 0 when every check passes, 1 otherwise, with one line per failure saying
exactly what broke. Usage: python scripts/integration_test.py
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import traceback
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore", category=DeprecationWarning)

import jsonschema  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

SCHEMAS = ROOT / "tests" / "contract" / "schemas"
FIXTURES = ROOT / "backend" / "fixtures"
FIXTURE_SCHEMAS = {
    "windows.json": "windows_response.json",
    "weather.json": "weather_probability_response.json",
    "skill.json": "skill_response.json",
    "site.json": "site_response.json",
    "ephemeris.json": "ephemeris_response.json",
}
# Fields that legitimately differ between identical requests.
NONDETERMINISTIC = {"computation_ms"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def registry() -> Registry:
    resources = []
    for path in SCHEMAS.glob("*.json"):
        schema = json.loads(path.read_text())
        resource = Resource.from_contents(schema)
        resources.append((path.name, resource))
        if "$id" in schema:
            resources.append((schema["$id"], resource))
    return Registry().with_resources(resources)


REGISTRY = registry()


def schema_errors(instance: object, schema_name: str) -> list[str]:
    schema = json.loads((SCHEMAS / schema_name).read_text())
    validator = jsonschema.Draft202012Validator(
        schema, registry=REGISTRY, format_checker=jsonschema.FormatChecker()
    )
    return [
        f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
        for e in validator.iter_errors(instance)
    ]


def windows_body(orbit: str) -> dict:
    start = dt.date.today()
    return {
        "target": {"type": orbit},
        "site": "canso",
        "vehicle_profile_id": "cyclone4m",
        "date_range": {"start": start.isoformat(), "end": (start + dt.timedelta(days=7)).isoformat()},
        "include_weather": True,
    }


def strip(value: object) -> object:
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in NONDETERMINISTIC}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def main() -> int:
    # (1) fixtures validate
    for fixture, schema_name in FIXTURE_SCHEMAS.items():
        path = FIXTURES / fixture
        if not path.is_file():
            check(f"fixture {fixture} validates", False, f"{path.relative_to(ROOT)} is missing")
            continue
        errors = schema_errors(json.loads(path.read_text()), schema_name)
        check(f"fixture {fixture} validates against {schema_name}", not errors, "; ".join(errors[:3]))

    # (2) app boots
    try:
        from fastapi.testclient import TestClient

        from backend.api.app import app

        client = TestClient(app)
        r = client.get("/v1/openapi.json")
        check("app boots and serves /v1/openapi.json", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as exc:  # the app failing to import is itself the finding
        check("app boots", False, f"{type(exc).__name__}: {exc}")
        return report()

    # (3) SSO, POLAR and LEO answered, and (4) the LEO 45.1 case
    responses: dict[str, dict] = {}
    for orbit in ("SSO", "POLAR", "LEO"):
        r = client.post("/v1/windows", json=windows_body(orbit))
        if not check(f"POST /v1/windows {orbit} returns 200", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}" if r.status_code != 200 else ""):
            continue
        body = responses[orbit] = r.json()
        errors = schema_errors(body, "windows_response.json")
        check(f"{orbit} response matches windows_response.json", not errors, "; ".join(errors[:3]))
        check(
            f"{orbit} response carries constants_block and provenance_block",
            bool(body.get("constants_block")) and bool(body.get("provenance_block")),
        )
        print(f"      engine_version={body.get('engine_version')} reachable={body.get('reachable')} windows={len(body.get('windows', []))}")
    for orbit in ("SSO", "POLAR"):
        if orbit in responses:
            body = responses[orbit]
            check(f"{orbit} is reachable with at least one window", body.get("reachable") is True and len(body.get("windows", [])) > 0,
                  f"reachable={body.get('reachable')}, windows={len(body.get('windows', []))}")
    if "LEO" in responses:
        leo = responses["LEO"]
        penalty = leo.get("plane_change_dv_ms")
        check(
            "LEO 45.1 returns reachable:false with a plane-change penalty",
            leo.get("reachable") is False and isinstance(penalty, (int, float)) and penalty > 0,
            f"reachable={leo.get('reachable')}, plane_change_dv_ms={penalty}",
        )

    # (5) site, weather and skill respond
    r = client.get("/v1/site")
    check("GET /v1/site returns 200 and matches site_response.json", r.status_code == 200 and not schema_errors(r.json(), "site_response.json"), f"HTTP {r.status_code}")
    wx_date = (dt.date.today() + dt.timedelta(days=3)).isoformat()
    r = client.get("/v1/weather/probability", params={"date": wx_date, "site": "canso"})
    ok = r.status_code == 200
    check(f"GET /v1/weather/probability {wx_date} returns 200 with horizon_label",
          ok and r.json().get("horizon_label") in ("FORECAST", "CLIMATOLOGY") and not schema_errors(r.json(), "weather_probability_response.json"),
          f"HTTP {r.status_code}" + (f", horizon_label={r.json().get('horizon_label')}" if ok else f": {r.text[:200]}"))
    skill_period = json.loads((FIXTURES / "skill.json").read_text()).get("period", {})
    params = {"period_start": skill_period.get("start", "2026-04-02"), "period_end": skill_period.get("end", "2026-09-27")}
    r = client.get("/v1/validation/skill", params=params)
    ok = r.status_code == 200
    series = r.json().get("skill_series", []) if ok else []
    check(f"GET /v1/validation/skill {params['period_start']}..{params['period_end']} returns a skill_series with n_cases",
          ok and len(series) > 0 and all("n_cases" in row for row in series) and not schema_errors(r.json(), "skill_response.json"),
          f"HTTP {r.status_code}, {len(series)} leads" if ok else f"HTTP {r.status_code}: {r.text[:200]}")

    # (6) citation resolves
    if "SSO" in responses:
        cid = responses["SSO"]["constants_block"]["citation_id"]
        r = client.get("/v1/citation", params={"id": cid})
        check(f"GET /v1/citation resolves {cid}", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            same = r.json().get("constants") == {k: v for k, v in responses["SSO"]["constants_block"].items() if k in r.json().get("constants", {})}
            check("citation reproduces the run's constants", same)

    # (7) determinism
    if "SSO" in responses:
        again = client.post("/v1/windows", json=windows_body("SSO")).json()
        check("identical SSO requests give identical results (computation_ms excluded)", strip(again) == strip(responses["SSO"]))

    return report()


def report() -> int:
    failed = [r for r in results if not r[1]]
    print()
    if failed:
        print(f"INTEGRATION FAILED: {len(failed)} of {len(results)} checks failed")
        for name, _, detail in failed:
            print(f"  - {name}" + (f": {detail}" if detail else ""))
        return 1
    print(f"INTEGRATION PASSED: {len(results)} checks")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        print("\nINTEGRATION FAILED: the harness itself crashed (traceback above)")
        sys.exit(1)
