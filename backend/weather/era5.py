"""Acquisition of the hourly observed archive used for climatology and verification.

Every model field is ERA5 reanalysis. Two routes lead to the same data: the Copernicus Climate Data Store, which
needs the key in CDSAPI_KEY (issue #3 W4, preferred), and an open route that needs no key (surface fields from
the Open-Meteo ERA5 archive, CAPE from the NSF NCAR ERA5 archive). Visibility is not a reanalysis field, so it is
the hourly observation of the nearest reporting station, with unreported hours filled from a named source and
listed. The archive is refused if any value is still missing. Both routes write the same field names.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import calendar
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from . import config, units
from .errors import WeatherDataError

CDS = "era5_cds"
OPEN = "open_data"
QUARTER_STARTS = (1, 4, 7, 10)


def missing_packages(names: list[str]) -> list[str]:
    """The names among the given Python packages that are not installed."""
    return [name for name in names if importlib.util.find_spec(name) is None]


def choose_source(preference: str, key_status: str, missing_packages: list[str]) -> tuple[str, str]:
    """Decide which route supplies the ERA5 fields and say why.

    preference is 'auto', 'era5_cds' or 'open_data'. With 'auto' the Copernicus route is used when the key is real
    and the download packages are installed, otherwise the open route. Asking for 'era5_cds' explicitly when it
    cannot work is an error, never a silent switch.
    """
    if preference == OPEN:
        return OPEN, "the open ERA5 route was requested explicitly"
    problem = None
    if key_status != "configured":
        problem = f"CDSAPI_KEY is {key_status} (set it in the environment or in backend/weather/.env)"
    elif missing_packages:
        problem = "the download packages are not installed: " + ", ".join(missing_packages)
    if problem is None:
        return CDS, "CDSAPI_KEY is set and the download packages are installed"
    if preference == CDS:
        raise WeatherDataError(f"the Copernicus CDS route was requested but {problem}")
    return OPEN, problem + "; the open ERA5 route was used"


# The open route: ERA5 without a key ------------------------------------------------------------------------

def _get(client: httpx.Client, url: str, params: dict, retries: int = 3) -> httpx.Response:
    """GET with retries on transport errors and non-200 answers. Raises WeatherDataError when all attempts fail."""
    problem = "no attempt made"
    for attempt in range(max(1, retries)):
        try:
            response = client.get(url, params=params)
            if response.status_code == 200:
                return response
            problem = f"HTTP {response.status_code}"
        except httpx.HTTPError as error:
            problem = type(error).__name__
        if attempt + 1 < max(1, retries):
            time.sleep(10 * (attempt + 1))
    raise WeatherDataError(f"{url} failed after {max(1, retries)} attempts: {problem}")


def _open_meteo_hourly(client: httpx.Client, part: dict, fields: list[str], site_cfg: dict, start: str,
                       end: str) -> dict:
    params = {
        "latitude": site_cfg["latitude_deg"],
        "longitude": site_cfg["longitude_deg"],
        "hourly": ",".join(fields),
        "models": part["model"],
        "start_date": start,
        "end_date": end,
        "timezone": "GMT",
    }
    body = _get(client, part["url"], params, part.get("retries", 3)).json()
    if body.get("utc_offset_seconds", 0) != 0:
        raise WeatherDataError(f"{part['url']} did not answer in UTC")
    return body


def _ncss_month(client: httpx.Client, cfg: dict, site_cfg: dict, year: int, month: int) -> dict[str, float]:
    """One month of an hourly ERA5 single-level variable at the grid point nearest the site, as {label: value}."""
    last_day = calendar.monthrange(year, month)[1]
    url = cfg["url_template"].format(yyyymm=f"{year}{month:02d}", last_day=f"{last_day:02d}")
    params = {
        "var": cfg["variable"],
        "latitude": site_cfg["latitude_deg"],
        "longitude": site_cfg["longitude_deg"],
        "time_start": f"{year}-{month:02d}-01T00:00:00Z",
        "time_end": f"{year}-{month:02d}-{last_day:02d}T23:00:00Z",
        "accept": "csv",
    }
    text = _get(client, url, params, cfg.get("retries", 3)).text
    values: dict[str, float] = {}
    for line in text.splitlines()[1:]:
        cells = line.split(",")
        if len(cells) >= 2 and cells[-1].strip():
            values[cells[0][:16]] = float(cells[-1])
    return values


def fetch_open_data(site_cfg: dict, cfg: dict, first_year: int, last_year: int, client: httpx.Client,
                    months: list[tuple[int, int]] | None = None, end_date: date | None = None,
                    cape_fetcher=None) -> dict:
    """ERA5 surface fields from the Open-Meteo ERA5 archive, and ERA5 CAPE.

    CAPE comes from cape_fetcher(first_year, end_date) when one is given (Copernicus), otherwise from the NSF
    NCAR ERA5 archive. With an end date the archive runs to that day and hours not yet published are trimmed from
    the end. Without one it covers first_year to last_year and any missing hour is an error. Values are returned
    as served, with the source unit of each field.
    """
    surface = cfg["era5_surface"]
    final_year = end_date.year if end_date else last_year
    times: list[str] = []
    columns: dict[str, list] = {field: [] for field in surface["fields"]}
    source_units: dict[str, str] = {}
    grid: dict = {}
    for year in range(first_year, final_year + 1):
        end = f"{year}-12-31"
        if end_date and year == end_date.year:
            end = min(end, end_date.isoformat())
        body = _open_meteo_hourly(client, surface, surface["fields"], site_cfg, f"{year}-01-01", end)
        times.extend(body["hourly"]["time"])
        grid = {key: body.get(key) for key in ("latitude", "longitude", "elevation")}
        for field in surface["fields"]:
            columns[field].extend(body["hourly"][field])
            source_units[field] = body["hourly_units"][field]
    field_sources = {field: f"era5 via {surface['url']} (models={surface['model']})" for field in surface["fields"]}

    cape_cfg = cfg["era5_cape"]
    if cape_fetcher is not None:
        cape, cape_source = cape_fetcher(first_year, end_date)
    else:
        months = months or [(year, month) for year in range(first_year, final_year + 1) for month in range(1, 13)]
        with ThreadPoolExecutor(max_workers=cape_cfg.get("parallel_requests", 1)) as pool:
            monthly = list(pool.map(lambda item: _ncss_month(client, cape_cfg, site_cfg, *item), months))
        cape = {label: value for values in monthly for label, value in values.items()}
        cape_source = f"era5 via NSF NCAR THREDDS, {cape_cfg['url_template'].split('{')[0]}"
    columns[cape_cfg["field"]] = [cape.get(label) for label in times]
    source_units[cape_cfg["field"]] = cape_cfg["unit"]
    field_sources[cape_cfg["field"]] = cape_source
    data = {"times": times, "columns": columns, "source_units": source_units, "field_sources": field_sources,
            "grid": grid, "gap_filled": {}}
    if end_date:
        data = trim_incomplete_tail(data)
    absent = [label for label, value in zip(data["times"], data["columns"][cape_cfg["field"]]) if value is None]
    if absent:
        raise WeatherDataError(f"ERA5 {cape_cfg['field']} is missing for {len(absent)} archive hours, "
                               f"first {absent[0]}; the archive was not written")
    return data


# Observed visibility ---------------------------------------------------------------------------------------

def add_observed_visibility(data: dict, site_cfg: dict, cfg: dict, client: httpx.Client) -> dict:
    """Add the visibility column: the station observation, with unreported hours filled from the named source.

    Returns a new archive. Every filled hour is recorded under gap_filled, so no value has a hidden origin.
    """
    station = cfg["station"]
    times = data["times"]
    observed: dict[str, float] = {}
    offset = 0
    while True:
        params = {
            "f": "json",
            "CLIMATE_IDENTIFIER": station["climate_identifier"],
            "datetime": f"{times[0][:10]} 00:00:00/{times[-1][:10]} 23:00:00",
            "limit": station["page_size"],
            "offset": offset,
            "sortby": "UTC_DATE",
            "properties": f"UTC_DATE,{station['property']}",
        }
        features = _get(client, station["url"], params).json().get("features", [])
        for feature in features:
            properties = feature["properties"]
            value = properties.get(station["property"])
            if value is not None:
                observed[properties["UTC_DATE"][:16]] = units.convert(float(value), station["source_unit"],
                                                                      cfg["unit"])
        if len(features) < station["page_size"]:
            break
        offset += station["page_size"]

    missing = [label for label in times if label not in observed]
    filled: dict[str, float | None] = {}
    gap = cfg["gap_fill"]
    if missing:
        first_day, last_day = times[0][:10], times[-1][:10]
        for year in sorted({label[:4] for label in missing}):
            # Never ask outside the archive period: the service refuses a request that reaches into the future.
            body = _open_meteo_hourly(client, gap, [gap["field"]], site_cfg, max(f"{year}-01-01", first_day),
                                      min(f"{year}-12-31", last_day))
            unit = body["hourly_units"][gap["field"]]
            for label, value in zip(body["hourly"]["time"], body["hourly"][gap["field"]]):
                filled[label] = None if value is None else units.convert(float(value), unit, cfg["unit"])
    column = [observed[label] if label in observed else filled.get(label) for label in times]
    gap_source = f"{gap['model']} via {gap['url']}"
    return {
        **data,
        "columns": {**data["columns"], cfg["field"]: column},
        "source_units": {**data["source_units"], cfg["field"]: cfg["unit"]},
        "field_sources": {**data["field_sources"], cfg["field"]: (
            f"observed at {station['station_name']} (ECCC climate id {station['climate_identifier']}) via "
            f"{station['url']}; unreported hours from {gap_source}")},
        "gap_filled": {**data.get("gap_filled", {}),
                       cfg["field"]: {"hours": len(missing), "times": missing, "source": gap_source}},
    }


def assert_complete(data: dict) -> None:
    """Raise WeatherDataError if any field has a missing value. The archive never contains a null."""
    holes = {field: sum(1 for value in column if value is None) for field, column in data["columns"].items()}
    holes = {field: count for field, count in holes.items() if count}
    if holes:
        raise WeatherDataError(f"the archive would contain missing values {holes}; it was not written")


# Preferred: ERA5 from the Copernicus Climate Data Store ----------------------------------------------------

def cds_area(latitude: float, longitude: float) -> list[float]:
    """North, west, south, east bounds of the 0.25 degree cells around a point, never of zero width or height."""
    north, south = math.ceil(latitude * 4) / 4, math.floor(latitude * 4) / 4
    west, east = math.floor(longitude * 4) / 4, math.ceil(longitude * 4) / 4
    if north == south:
        north += 0.25
    if east == west:
        east += 0.25
    return [north, west, south, east]


def cds_tasks(first_year: int, end_date: date | None, last_year: int | None = None,
              months_per_request: int = 3) -> list[tuple]:
    """The requests that cover the period, as (year, months, days). days is None for whole months.

    Months are grouped months_per_request at a time within a year. When an end date is given, the month that
    holds it is requested on its own with only the days up to it, so that no unpublished day is asked for.
    """
    end = end_date or date(last_year, 12, 31)
    tasks: list[tuple] = []
    for year in range(first_year, end.year + 1):
        for first_month in range(1, 13, months_per_request):
            months = [month for month in range(first_month, min(first_month + months_per_request, 13))
                      if (year, month) <= (end.year, end.month)]
            partial = (year == end.year and end.month in months
                       and end.day < calendar.monthrange(end.year, end.month)[1])
            whole = [month for month in months if not (partial and month == end.month)]
            if whole:
                tasks.append((year, whole, None))
            if partial:
                tasks.append((year, [end.month], list(range(1, end.day + 1))))
    return tasks


def cds_request(cfg: dict, kind: str, site_cfg: dict, year: int, first_month: int | None = None,
                months: list[int] | None = None, days: list[int] | None = None) -> dict:
    """The dataset name and request body. kind is 'single' or 'pressure'. Default: the quarter from first_month."""
    months = months or list(range(first_month, first_month + 3))
    request = {
        "product_type": ["reanalysis"],
        "year": [str(year)],
        "month": [f"{month:02d}" for month in months],
        "day": [f"{day:02d}" for day in (days or range(1, 32))],
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "area": cds_area(site_cfg["latitude_deg"], site_cfg["longitude_deg"]),
        "data_format": "netcdf",
    }
    if kind == "single":
        return {"dataset": cfg["single_levels_dataset"], "request": {**request,
                                                                     "variable": cfg["single_level_variables"]}}
    return {"dataset": cfg["pressure_levels_dataset"],
            "request": {**request, "variable": cfg["pressure_level_variables"],
                        "pressure_level": [str(level) for level in cfg["pressure_levels_hpa"]]}}


def read_cds_point(paths: list[Path], latitude: float, longitude: float) -> tuple[list[str], dict[str, list]]:
    """The hourly series at the grid point nearest the site from CDS NetCDF files.

    Returns the UTC labels and one list per variable short name. A pressure-level variable becomes one entry per
    level, named by short name and level, for example u850. Needs the xarray and netCDF4 packages.
    """
    import xarray

    series: dict[str, dict[str, float | None]] = {}
    for path in paths:
        with xarray.open_dataset(path) as dataset:
            time_name = "valid_time" if "valid_time" in dataset.coords else "time"
            point = dataset.sel(latitude=latitude, longitude=longitude, method="nearest")
            labels = [str(stamp)[:13] + ":00" for stamp in point[time_name].values.astype("datetime64[h]")]
            for name, array in point.data_vars.items():
                if time_name not in array.dims:
                    continue
                if "pressure_level" in array.dims:
                    for level in array["pressure_level"].values:
                        values = array.sel(pressure_level=level).values
                        series.setdefault(f"{name}{int(level)}", {}).update(zip(labels, values.tolist()))
                elif array.ndim == 1:
                    series.setdefault(name, {}).update(zip(labels, array.values.tolist()))
    all_labels = sorted({label for by_time in series.values() for label in by_time})
    point_values = {}
    for name, by_time in series.items():
        column = [by_time.get(label) for label in all_labels]
        point_values[name] = [None if value is None or value != value else float(value) for value in column]
    return all_labels, point_values


def wind_direction_from(u: float, v: float) -> float:
    """Meteorological wind direction in degrees: the direction the wind blows from, 0 for north, 90 for east."""
    return (180.0 + math.degrees(math.atan2(u, v))) % 360.0


def cds_point_to_columns(point: dict[str, list], levels: list[int], snowfall_cm_per_mm_water: float,
                         precision_mm: float | None = None) -> tuple[dict[str, list], dict[str, str]]:
    """Convert ERA5 short-name series into the field names and units the criteria use.

    With precision_mm, precipitation and snowfall water equivalent are rounded to that precision, which is the
    precision of the forecast data. Unrounded ERA5 holds trace amounts that the forecast data cannot show.
    """
    needed = ["u10", "v10", "fg10", "t2m", "tp", "sf", "tcc", "lcc", "mcc", "cape"]
    needed += [f"{component}{level}" for level in levels for component in ("u", "v")]
    absent = [name for name in needed if name not in point]
    if absent:
        raise WeatherDataError(f"the CDS files lack the variables {absent}")

    def each(values, function):
        return [None if value is None else round(function(value), 4) for value in values]

    def reported(millimetres: float) -> float:
        if precision_mm is None:
            return millimetres
        return round(millimetres / precision_mm) * precision_mm

    def pair(first, second, function):
        return [None if a is None or b is None else round(function(a, b), 4) for a, b in zip(first, second)]

    columns = {
        "wind_speed_10m": pair(point["u10"], point["v10"], math.hypot),
        "wind_gusts_10m": each(point["fg10"], float),
        "wind_direction_10m": pair(point["u10"], point["v10"], wind_direction_from),
        "temperature_2m": each(point["t2m"], lambda kelvin: kelvin - 273.15),
        "precipitation": each(point["tp"], lambda metres: reported(metres * 1000.0)),
        "snowfall": each(point["sf"], lambda metres: reported(metres * 1000.0) * snowfall_cm_per_mm_water),
        "cloud_cover": each(point["tcc"], lambda fraction: fraction * 100.0),
        "cloud_cover_low": each(point["lcc"], lambda fraction: fraction * 100.0),
        "cloud_cover_mid": each(point["mcc"], lambda fraction: fraction * 100.0),
        "cape": each(point["cape"], float),
    }
    units = {"wind_speed_10m": "m/s", "wind_gusts_10m": "m/s", "wind_direction_10m": "°",
             "temperature_2m": "°C", "precipitation": "mm", "snowfall": "cm", "cloud_cover": "%",
             "cloud_cover_low": "%", "cloud_cover_mid": "%", "cape": "J/kg"}
    for level in levels:
        columns[f"wind_speed_{level}hPa"] = pair(point[f"u{level}"], point[f"v{level}"], math.hypot)
        units[f"wind_speed_{level}hPa"] = "m/s"
    return columns, units


def trim_incomplete_tail(data: dict) -> dict:
    """Drop the hours at the end for which a field has no value yet. Nothing in the middle is touched."""
    keep = len(data["times"])
    while keep > 0 and any(column[keep - 1] is None for column in data["columns"].values()):
        keep -= 1
    return {**data, "times": data["times"][:keep],
            "columns": {field: column[:keep] for field, column in data["columns"].items()}}


def _cds_series(site_cfg: dict, cfg: dict, variables: list[str], months_per_request: int, first_year: int,
                last_year: int, credentials: dict, workdir: Path, end_date: date | None,
                tag: str) -> tuple[list[str], dict[str, list]]:
    """Download the given single-level variables from Copernicus and return (labels, series by short name).

    Requests already present in workdir are not downloaded again. Needs the cdsapi, xarray and netCDF4 packages.
    """
    import cdsapi

    tasks = cds_tasks(first_year, end_date, last_year, months_per_request)

    def download(task: tuple) -> Path:
        year, months, days = task
        name = f"{tag}_{year}_{months[0]:02d}_{months[-1]:02d}" + (f"_d{days[-1]:02d}" if days else "")
        folder = workdir / name
        if any(folder.glob("*.nc")):
            return folder
        folder.mkdir(parents=True, exist_ok=True)
        spec = cds_request({**cfg, "single_level_variables": variables}, "single", site_cfg, year,
                           months=list(months), days=list(days) if days else None)
        target = workdir / f"{name}.download"
        client = cdsapi.Client(url=credentials["url"], key=credentials["key"], quiet=True)
        client.retrieve(spec["dataset"], spec["request"], str(target))
        # CDS returns a zip when instantaneous, accumulated and maximum variables are mixed in one request.
        if zipfile.is_zipfile(target):
            with zipfile.ZipFile(target) as archive:
                archive.extractall(folder)
            target.unlink()
        else:
            target.rename(folder / "data.nc")
        print(f"ERA5 {tag} {year} months {months[0]} to {months[-1]}: downloaded", flush=True)
        return folder

    with ThreadPoolExecutor(max_workers=cfg["max_parallel_requests"]) as pool:
        folders = list(pool.map(download, tasks))

    series: dict[str, dict[str, float | None]] = {}
    for folder in folders:
        labels, values = read_cds_point(sorted(folder.glob("*.nc")), site_cfg["latitude_deg"],
                                        site_cfg["longitude_deg"])
        for name, column in values.items():
            series.setdefault(name, {}).update(zip(labels, column))
    times = sorted({label for column in series.values() for label in column})
    return times, {name: [column.get(label) for label in times] for name, column in series.items()}


def fetch_cds(site_cfg: dict, cfg: dict, first_year: int, last_year: int, credentials: dict, workdir: Path,
              end_date: date | None = None) -> dict:
    """Every ERA5 field from Copernicus, in evaluation units. Runs to end_date when given, else to last_year."""
    times, aligned = _cds_series(site_cfg, cfg, cfg["single_level_variables"], cfg["months_per_request"],
                                 first_year, last_year, credentials, workdir, end_date, "single")
    columns, units = cds_point_to_columns(aligned, cfg["pressure_levels_hpa"], cfg["snowfall_cm_per_mm_water"],
                                          cfg.get("precision_mm"))
    north, west, south, east = cds_area(site_cfg["latitude_deg"], site_cfg["longitude_deg"])
    return trim_incomplete_tail({
        "times": times,
        "columns": columns,
        "source_units": units,
        "field_sources": {field: f"era5 via Copernicus CDS, {cfg['single_levels_dataset']}" for field in columns},
        "grid": {"latitude": round(site_cfg["latitude_deg"] * 4) / 4,
                 "longitude": round(site_cfg["longitude_deg"] * 4) / 4,
                 "requested_area_north_west_south_east": [north, west, south, east]},
        "gap_filled": {},
    })


def fetch_cds_cape(site_cfg: dict, cfg: dict, first_year: int, last_year: int, credentials: dict, workdir: Path,
                   end_date: date | None = None) -> tuple[dict[str, float], str]:
    """Hourly ERA5 CAPE from Copernicus as {label: J/kg}, and the text that names the source."""
    times, aligned = _cds_series(site_cfg, cfg, ["convective_available_potential_energy"],
                                 cfg["cape_months_per_request"], first_year, last_year, credentials, workdir,
                                 end_date, "cape")
    values = {label: round(value, 4) for label, value in zip(times, aligned["cape"]) if value is not None}
    return values, f"era5 via Copernicus CDS, {cfg['single_levels_dataset']}"


def acquire(site_cfg: dict, archive_cfg: dict, preference: str, key_status: str, credentials: dict | None,
            missing: list[str], first_year: int | None, last_year: int | None, workdir: Path | None,
            client: httpx.Client | None, cds_fetcher=None, open_fetcher=None, visibility_fetcher=None,
            completeness_check=None, end_date: date | None = None) -> tuple[dict, str, str]:
    """Build the archive: ERA5 fields by the chosen route, then observed visibility. Returns (data, source, reason).

    With preference 'auto', a Copernicus download that fails switches to the open ERA5 route, and the reason
    records the failure by error type only, so that no key can leak into a file. With preference 'era5_cds' a
    failure is raised. end_date extends the Copernicus route past last_year to that day. The result is checked for
    completeness before it is returned.
    """
    cds_fetcher = cds_fetcher or fetch_cds
    open_fetcher = open_fetcher or fetch_open_data
    visibility_fetcher = visibility_fetcher or add_observed_visibility
    completeness_check = completeness_check or assert_complete
    first_year = first_year or archive_cfg["first_year"]
    last_year = last_year or archive_cfg["last_year"]
    source, reason = choose_source(preference, key_status, missing)
    data = None
    if source == CDS:
        try:
            extra = {"end_date": end_date} if end_date is not None else {}
            data = cds_fetcher(site_cfg, archive_cfg[CDS], first_year, last_year, credentials, workdir, **extra)
        except Exception as error:
            if preference == CDS:
                raise
            source = OPEN
            reason = (f"the Copernicus CDS download failed with {type(error).__name__}; "
                      "the open ERA5 route was used")
    if data is None:
        extra = {}
        if key_status == "configured" and not missing:
            extra = {"end_date": end_date,
                     "cape_fetcher": lambda first, end: fetch_cds_cape(site_cfg, archive_cfg[CDS], first, last_year,
                                                                       credentials, workdir, end)}
        data = open_fetcher(site_cfg, archive_cfg[OPEN], first_year, last_year, client, **extra)
    data = visibility_fetcher(data, site_cfg, archive_cfg["visibility_observed"], client)
    completeness_check(data)
    return data, source, reason


# Writing ---------------------------------------------------------------------------------------------------

def drop_constant_fields(columns: dict[str, list]) -> tuple[dict[str, list], list[str]]:
    """Remove fields that hold one constant value for the whole period. Such a field is not data."""
    kept, dropped = {}, []
    for field, values in columns.items():
        if len({value for value in values if value is not None}) > 1:
            kept[field] = values
        else:
            dropped.append(field)
    return kept, dropped


def write_archive(site: str, data: dict, acquisition: str, reason: str, dropped: list[str],
                  directory: Path | None = None, retrieved_at: str | None = None) -> dict:
    """Write data/era5_<site>_hourly.csv.gz and its metadata file. Returns the metadata."""
    directory = directory or config.DATA_DIR
    archive_cfg = config.load_sources()["climatology_archive"]
    fields = list(data["columns"])
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow(["time_utc"] + fields)
    for position, label in enumerate(data["times"]):
        writer.writerow([label] + ["" if data["columns"][field][position] is None
                                   else data["columns"][field][position] for field in fields])
    raw = text.getvalue().encode("utf-8")
    path = directory / f"era5_{site}_hourly.csv.gz"
    with open(path, "wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as zipped:
            zipped.write(raw)
    meta = {
        "site": site,
        "acquisition": acquisition,
        "acquisition_reason": reason,
        "source": archive_cfg["description"],
        "licence": archive_cfg["licence"],
        "grid_cell": data["grid"],
        "period_start": data["times"][0],
        "period_end": data["times"][-1],
        "time_basis": "UTC; a value labelled T is instantaneous at T, or the total or maximum of the hour ending at T",
        "hours": len(data["times"]),
        "fields": fields,
        "source_units": {field: data["source_units"][field] for field in fields},
        "field_sources": {field: data["field_sources"][field] for field in fields},
        "missing_values": {field: sum(1 for value in data["columns"][field] if value is None)
                           for field in fields},
        "gap_filled": data.get("gap_filled", {}),
        "dropped_constant_fields": dropped,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "csv_sha256": hashlib.sha256(raw).hexdigest(),
        "file": path.name,
    }
    (directory / f"era5_{site}_hourly.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta
