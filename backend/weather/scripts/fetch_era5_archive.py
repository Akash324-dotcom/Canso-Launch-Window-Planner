"""Build the hourly observed archive data/era5_<site>_hourly.csv.gz and its metadata.

    python -m backend.weather.scripts.fetch_era5_archive canso
    python -m backend.weather.scripts.fetch_era5_archive canso --source era5_cds
    python -m backend.weather.scripts.fetch_era5_archive canso --source open_data

Every model field is ERA5. Source 'auto' (the default) takes it from the Copernicus Climate Data Store when
CDSAPI_KEY holds a real token and cdsapi, xarray and netCDF4 are installed, otherwise from the open route (the
Open-Meteo ERA5 archive for surface fields and the NSF NCAR ERA5 archive for CAPE), which needs no key.
Visibility is the hourly observation of the configured ECCC station. The archive is written only if it has no
missing value. The key is read from the environment or from backend/weather/.env; see .env.example.
Run from the repository root. Needs the network. After it, run build_climatology.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import httpx

from backend.weather import config, credentials, era5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("site")
    parser.add_argument("--source", choices=["auto", era5.CDS, era5.OPEN], default="auto")
    parser.add_argument("--first-year", type=int)
    parser.add_argument("--last-year", type=int)
    parser.add_argument("--no-extension", action="store_true",
                        help="stop at the end of last_year instead of extending to the latest published day")
    arguments = parser.parse_args()

    site_cfg = config.load_site(arguments.site)
    archive_cfg = config.load_sources()["climatology_archive"]
    print(credentials.describe_cds())
    missing = era5.missing_packages(archive_cfg[era5.CDS]["python_packages"])
    end_date = None
    if not arguments.no_extension and not arguments.last_year:
        end_date = datetime.now(timezone.utc).date() - timedelta(days=archive_cfg[era5.CDS]["latency_days"])
    workdir = config.DATA_DIR.parent / "cache" / "era5_cds" / arguments.site
    workdir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120) as client:
        data, source, reason = era5.acquire(
            site_cfg, archive_cfg, arguments.source, key_status=credentials.cds_status(),
            credentials=credentials.cds_credentials(), missing=missing, first_year=arguments.first_year,
            last_year=arguments.last_year, workdir=workdir, client=client, end_date=end_date)
    print(f"archive source: {source} ({reason})")

    data["columns"], dropped = era5.drop_constant_fields(data["columns"])
    meta = era5.write_archive(arguments.site, data, acquisition=source, reason=reason, dropped=dropped)
    print(f"wrote {meta['file']}: {meta['hours']} hours, {meta['period_start']} to {meta['period_end']}, "
          f"{len(meta['fields'])} fields, dropped constant fields {dropped}")
    print("missing values per field:", meta["missing_values"])
    for field, gap in meta["gap_filled"].items():
        print(f"gap-filled {field}: {gap['hours']} hours from {gap['source']}")


if __name__ == "__main__":
    main()
