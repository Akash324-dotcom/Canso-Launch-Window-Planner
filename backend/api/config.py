"""Configuration for the /v1 service, loaded from ``backend/api/data``.

Spec II.10 forbids hard-coding anything site-, vehicle- or criteria-dependent in
source, and spec IV.8 puts the rate limits in configuration rather than in code.
This module is the only reader of those files; every other module receives a
``Settings`` instance. That indirection is also what makes the service testable:
``Settings.load`` accepts another data directory and ``with_fixture_overrides``
returns a copy pointing at other offline documents, so a test can change the
configuration without editing a shipped file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.api.errors import UnknownResourceError

API_DIR = Path(__file__).resolve().parent
REPO_ROOT = API_DIR.parents[1]
DATA_DIR = API_DIR / "data"
ENGINE_DIR = REPO_ROOT / "backend" / "engine"
ENGINE_SITE_DIR = ENGINE_DIR / "data"
CONFIG_DIR_ENV = "LAUNCHWIN_DATA_DIR"
REPO_ROOT_ENV = "LAUNCHWIN_REPO_ROOT"


def repo_root() -> Path:
    """Root of the repository, so that recorded paths resolve from any cwd."""
    override = os.environ.get(REPO_ROOT_ENV)
    return Path(override) if override else REPO_ROOT


@lru_cache(maxsize=1)
def _default_settings() -> "Settings":
    return Settings.load()


def get_settings() -> "Settings":
    """FastAPI dependency returning the process wide settings.

    A dependency rather than a module global so that a test can substitute settings
    through ``app.dependency_overrides`` without editing a file.
    """
    return _default_settings()


@dataclass(frozen=True)
class Settings:
    """The service configuration, with the paths it was read from."""

    service: dict[str, Any]
    constants_path: Path
    data_dir: Path
    root: Path
    sites: dict[str, Path] = field(default_factory=dict)
    runs_dir_override: Path | None = None

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, data_dir: Path | None = None) -> "Settings":
        directory = Path(data_dir) if data_dir else Path(os.environ.get(CONFIG_DIR_ENV, DATA_DIR))
        service = json.loads((directory / "service.json").read_text(encoding="utf-8"))
        sites = {path.stem: path for path in sorted((directory / "sites").glob("*.json"))}
        return cls(
            service=service,
            constants_path=directory / "constants.json",
            data_dir=directory,
            root=repo_root(),
            sites=sites,
        )

    def with_fixture_overrides(self, **fixtures: str) -> "Settings":
        """A copy whose offline fixture paths are replaced. Used by tests."""
        return replace(self, service={**self.service, "fixtures": {**self.fixture_paths, **fixtures}})

    def with_service_overrides(self, section: str, **values: Any) -> "Settings":
        """A copy with one configuration section partially replaced. Used by tests."""
        return replace(self, service={**self.service, section: {**self.service[section], **values}})

    def with_runs_dir(self, path: Path | str) -> "Settings":
        """A copy whose stored run records go elsewhere. Used by tests."""
        return replace(self, runs_dir_override=Path(path))

    # ----------------------------------------------------------- accessors

    @property
    def service_path(self) -> Path:
        return self.data_dir / "service.json"

    @property
    def api_prefix(self) -> str:
        return str(self.service["service"]["api_prefix"])

    @property
    def default_site(self) -> str:
        return str(self.service["service"]["default_site"])

    @property
    def default_include_weather(self) -> bool:
        return bool(self.service["service"]["default_include_weather"])

    @property
    def default_criteria_version(self) -> str:
        return str(self.service["service"]["default_criteria_version"])

    @property
    def criteria_file(self) -> Path:
        return self.resolve(self.service["service"]["criteria_file"])

    @property
    def target_classes(self) -> dict[str, Any]:
        return self.service["target_classes"]

    @property
    def sso(self) -> dict[str, Any]:
        return self.service["sso"]

    @property
    def fixture_paths(self) -> dict[str, str]:
        return dict(self.service["fixtures"])

    @property
    def retry_after_s(self) -> dict[str, int]:
        return {key: int(value) for key, value in self.service["retry_after_s"].items()}

    @property
    def cache_config(self) -> dict[str, Any]:
        """Spec IV.8 cache lifetimes, in seconds. Zero means that cache is off."""
        return dict(self.service["cache"])

    @property
    def rate_limit_config(self) -> dict[str, Any]:
        """Spec IV.8 request budgets. Never a literal in source."""
        return dict(self.service["rate_limit"])

    @property
    def ephemeris_config(self) -> dict[str, Any]:
        return dict(self.service["ephemeris"])

    @property
    def skill_config(self) -> dict[str, Any]:
        return dict(self.service["skill"])

    @property
    def orbits_config(self) -> dict[str, Any]:
        return dict(self.service["orbits"])

    @property
    def site_config(self) -> dict[str, Any]:
        return dict(self.service["site"])

    @property
    def provenance_table(self) -> dict[str, Any]:
        """The spec II.10 provenance table, serialised by GET /v1/citation."""
        return json.loads((self.data_dir / "provenance_table.json").read_text(encoding="utf-8"))

    def base_track_path(self, orbit_id: str) -> Path:
        """Path of the recorded offline ground-track segment for one orbit id."""
        return self.resolve(self.ephemeris_config["base_tracks"][orbit_id])

    def run_record_path(self, citation_id: str) -> Path:
        """Path of one stored run record, spec IV.6."""
        return self.runs_dir / f"{citation_id}.json"

    def fixture_path(self, name: str) -> Path:
        """Absolute path of one offline fixture document."""
        return self.resolve(self.fixture_paths[name])

    def resolve(self, relative: str) -> Path:
        return self.root / relative

    def relative(self, path: Path) -> str:
        """Repository-relative form of a path, for the provenance source_files."""
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    # ----------------------------------------------------------------- sites

    def site_path(self, site_id: str) -> Path:
        """Path of the API's site record for ``site_id``, the spec IV.5 fields."""
        try:
            return self.sites[site_id]
        except KeyError:
            raise UnknownResourceError("site", site_id) from None

    def engine_site_path(self, site_id: str) -> Path:
        """Path of the site file ENGINE owns and the engine reads for ``site_id``."""
        return ENGINE_SITE_DIR / f"site_{site_id}.json"

    def engine_site_corridor(self, site_id: str) -> dict[str, Any] | None:
        """The corridor of the engine's site file, or None when the engine ships none."""
        path = self.engine_site_path(site_id)
        if not path.is_file():
            return None
        corridor = json.loads(path.read_text(encoding="utf-8")).get("corridor") or {}
        if corridor.get("A_min_deg") is None or corridor.get("A_max_deg") is None:
            return None
        return corridor

    def site_document(self, site_id: str) -> dict[str, Any]:
        """The site record, with the corridor the engine applies.

        The record is the API's file. Its corridor was a placeholder of the API
        (90 to 200 deg, ASSUMPTION) while the engine judged rows by the corridor of
        its own site file, so the service reported one corridor and applied another.
        When the engine ships a site file its corridor, source and flags replace the
        placeholder; without one the record answers as before.
        """
        document = json.loads(self.site_path(site_id).read_text(encoding="utf-8"))
        corridor = self.engine_site_corridor(site_id)
        if corridor is None:
            return document
        flags = corridor.get("flags") or {}
        low = str(flags.get("A_min_deg", corridor.get("flag", "ASSUMPTION")))
        high = str(flags.get("A_max_deg", corridor.get("flag", "ASSUMPTION")))
        document["corridor"] = {
            "A_min_deg": corridor["A_min_deg"],
            "A_max_deg": corridor["A_max_deg"],
            "source": str(corridor.get("source", "")),
            "flag": low if low == high else f"{low} (A_min_deg), {high} (A_max_deg)",
        }
        row_flags = dict(document.get("row_flags", {}))
        row_flags["corridor_A_min_deg"] = low
        row_flags["corridor_A_max_deg"] = high
        document["row_flags"] = row_flags
        document["corridor_file"] = self.relative(self.engine_site_path(site_id))
        return document

    @property
    def runs_dir(self) -> Path:
        """Directory the stored run records are written to."""
        return self.runs_dir_override or self.resolve(self.service["runs_dir"])

    def vehicle_profile_path(self, vehicle_profile_id: str) -> Path:
        """Path of the vehicle profile document, which ENGINE owns.

        The API never writes there. The path is resolved so that the provenance
        block can report the vehicle file when it exists; until ENGINE lands it
        does not, and the block then records no vehicle row flags rather than
        inventing any.
        """
        return ENGINE_DIR / "data" / "vehicles" / f"{vehicle_profile_id}.json"