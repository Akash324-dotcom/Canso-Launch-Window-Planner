"""Credentials: keys are read from the environment, a placeholder is never treated as a key, nothing leaks."""

from __future__ import annotations

from backend.weather import credentials

URL = "https://cds.climate.copernicus.eu/api"


def test_the_committed_example_file_holds_a_placeholder_not_a_key():
    example = credentials.read_env_file(credentials.ENV_EXAMPLE_FILE)

    assert example["CDSAPI_URL"] == URL
    assert credentials.is_placeholder(example["CDSAPI_KEY"])


def test_a_placeholder_or_missing_key_is_reported_as_not_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    env_file = tmp_path / ".env"

    monkeypatch.setattr(credentials, "ENV_FILE", env_file)
    assert credentials.cds_credentials() is None
    assert credentials.cds_status() == "missing"

    env_file.write_text("CDSAPI_URL=" + URL + "\nCDSAPI_KEY=REPLACE_WITH_YOUR_CDS_PERSONAL_ACCESS_TOKEN\n")
    assert credentials.cds_credentials() is None
    assert credentials.cds_status() == "placeholder"


def test_a_real_key_in_the_env_file_is_used(monkeypatch, tmp_path):
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nCDSAPI_URL=" + URL + "\nCDSAPI_KEY = 'abcd-1234'\n")
    monkeypatch.setattr(credentials, "ENV_FILE", env_file)

    assert credentials.cds_credentials() == {"url": URL, "key": "abcd-1234"}
    assert credentials.cds_status() == "configured"


def test_the_process_environment_takes_precedence_over_the_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CDSAPI_URL=" + URL + "\nCDSAPI_KEY=from-file\n")
    monkeypatch.setattr(credentials, "ENV_FILE", env_file)
    monkeypatch.setenv("CDSAPI_KEY", "from-environment")

    assert credentials.cds_credentials()["key"] == "from-environment"


def test_the_status_text_never_contains_the_key(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("CDSAPI_URL=" + URL + "\nCDSAPI_KEY=super-secret-token\n")
    monkeypatch.setattr(credentials, "ENV_FILE", env_file)
    monkeypatch.delenv("CDSAPI_KEY", raising=False)

    assert "super-secret-token" not in credentials.cds_status()
    assert "super-secret-token" not in credentials.describe_cds()


def test_the_real_env_file_is_ignored_by_git_and_the_example_is_not():
    ignore = (credentials.ENV_FILE.parent / ".gitignore").read_text(encoding="utf-8").split()

    assert ".env" in ignore
    assert ".env.example" not in ignore
