"""API credentials for the weather layer.

The project documents name no key file. They say: "No credentials in code; the app reads paths and keys from
environment" (docs/03_WORKFLOW_API.md) and "No credentials in code or commits" (docs/issues/issue-04-API.md).
So every key is an environment variable. For convenience the variables may also be written in
backend/weather/.env, which git ignores; a variable set in the process environment wins over the file.
backend/weather/.env.example is the committed template and holds placeholders only.

Variables:
    CDSAPI_URL   Copernicus Climate Data Store API address
    CDSAPI_KEY   Copernicus Climate Data Store personal access token (ERA5)

These are the names the official cdsapi client reads. The key value is never printed or logged by this module.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"
ENV_EXAMPLE_FILE = Path(__file__).resolve().parent / ".env.example"
PLACEHOLDER_PREFIX = "REPLACE_WITH"
CDS_URL_VARIABLE = "CDSAPI_URL"
CDS_KEY_VARIABLE = "CDSAPI_KEY"


def read_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Blank lines and lines starting with # are skipped; quotes around a value are removed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip("'\"")
    return values


def get(name: str) -> str | None:
    """One variable: the process environment first, then backend/weather/.env. Empty counts as absent."""
    value = os.environ.get(name) or read_env_file(ENV_FILE).get(name)
    return value or None


def is_placeholder(value: str | None) -> bool:
    return bool(value) and value.startswith(PLACEHOLDER_PREFIX)


def cds_status() -> str:
    """'configured', 'placeholder' or 'missing'. Never contains the key."""
    key = get(CDS_KEY_VARIABLE)
    if not key or not get(CDS_URL_VARIABLE):
        return "missing"
    return "placeholder" if is_placeholder(key) else "configured"


def cds_credentials() -> dict[str, str] | None:
    """The CDS address and key, or None when the key is absent or still the placeholder."""
    if cds_status() != "configured":
        return None
    return {"url": get(CDS_URL_VARIABLE), "key": get(CDS_KEY_VARIABLE)}


def describe_cds() -> str:
    """One line for logs and progress notes. Never contains the key."""
    return {
        "configured": f"{CDS_KEY_VARIABLE} is set; the Copernicus CDS path can be used",
        "placeholder": f"{CDS_KEY_VARIABLE} still holds the placeholder; the Copernicus CDS path is not usable yet",
        "missing": f"{CDS_KEY_VARIABLE} or {CDS_URL_VARIABLE} is not set; the Copernicus CDS path is not usable",
    }[cds_status()]
