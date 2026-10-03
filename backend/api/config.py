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
        """Path of the site document for ``site_id``.

        ENGINE owns ``backend/engine/data/site_canso.json``; it wins when present,
        so that provenance reports the file the engine actually reads. The API
        owned copy is the fallback until ENGINE lands.
        """
        engine_owned = ENGINE_SITE_DIR / f"{site_id}.json"
        if engine_owned.is_file():
            return engine_owned
        try:
            return self.sites[site_id]
        except KeyError:
            raise UnknownResourceError("site", site_id) from None

    def site_document(self, site_id: str) -> dict[str, Any]:
        return json.loads(self.site_path(site_id).read_text(encoding="utf-8"))

    def vehicle_profile_path(self, vehicle_profile_id: str) -> Path:
        """Path of the vehicle profile document, which ENGINE owns.

        The API never writes there. The path is resolved so that the provenance
        block can report the vehicle file when it exists; until ENGINE lands it
        does not, and the block then records no vehicle row flags rather than
        inventing any.
        """
        return ENGINE_DIR / "data" / "vehicles" / f"{vehicle_profile_id}.json"