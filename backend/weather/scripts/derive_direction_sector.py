"""Compute the wind direction sector of criteria_v1 from published coordinates. Nothing in it is chosen.

    python -m backend.weather.scripts.derive_direction_sector canso

The Canso environmental assessment says the wind go-no go criteria exist "to ensure any cloud is well away and/or
aloft from any populated areas up range", and it names the communities next to the site. The sector is therefore
the set of wind directions that blow from the site centre toward those communities: for each community, the
bearing from the site to it, turned by 180 degrees to give the direction the wind comes from. The site centre is
the one printed in the assessment; the community coordinates are from the Canadian Geographical Names Database.
Both are stored with their sources in data/sites.json. The script prints the sector and changes no file.
"""

from __future__ import annotations

import math
import sys

from backend.weather import config


def initial_bearing(latitude_1: float, longitude_1: float, latitude_2: float, longitude_2: float) -> float:
    """Great-circle initial bearing from point 1 to point 2, in degrees clockwise from north."""
    phi_1, phi_2 = math.radians(latitude_1), math.radians(latitude_2)
    delta = math.radians(longitude_2 - longitude_1)
    east = math.sin(delta) * math.cos(phi_2)
    north = math.cos(phi_1) * math.sin(phi_2) - math.sin(phi_1) * math.cos(phi_2) * math.cos(delta)
    return math.degrees(math.atan2(east, north)) % 360.0


def wind_from(bearing_to_place: float) -> float:
    """The direction a wind comes from when it blows toward the given bearing."""
    return (bearing_to_place + 180.0) % 360.0


def place_directions(site_cfg: dict) -> list[tuple[str, float, float]]:
    """For each populated place: its name, the bearing from the site to it, and the wind direction toward it."""
    result = []
    for place in site_cfg["populated_places"]["places"]:
        bearing = initial_bearing(site_cfg["latitude_deg"], site_cfg["longitude_deg"],
                                  place["latitude_deg"], place["longitude_deg"])
        result.append((place["name"], bearing, wind_from(bearing)))
    return result


def sector(site_cfg: dict) -> tuple[float, float]:
    """The smallest and largest wind direction that blows toward a populated place.

    The places must span less than 180 degrees as seen from the site and must not straddle north in wind-from
    terms; otherwise a single interval cannot describe the sector and the function refuses.
    """
    directions = sorted(direction for _, _, direction in place_directions(site_cfg))
    if directions[-1] - directions[0] >= 180.0:
        raise ValueError("the populated places do not form one sector of less than 180 degrees")
    return directions[0], directions[-1]


def main(site: str) -> None:
    site_cfg = config.load_site(site)
    print(f"site centre: {site_cfg['latitude_deg']}, {site_cfg['longitude_deg']}")
    for name, bearing, direction in place_directions(site_cfg):
        print(f"{name}: bearing from site {bearing:.1f} deg; wind from {direction:.1f} deg blows toward it")
    low, high = sector(site_cfg)
    print(f"sector: wind from {low:.1f} to {high:.1f} deg")


if __name__ == "__main__":
    main(sys.argv[1])
