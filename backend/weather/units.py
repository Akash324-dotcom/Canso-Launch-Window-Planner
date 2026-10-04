"""Explicit unit conversion. Every value read from a data source passes through here before it meets a limit."""

from __future__ import annotations

from .errors import WeatherDataError

# Factor to the base unit of each dimension.
_SPEED_TO_MS = {"m/s": 1.0, "km/h": 1.0 / 3.6, "kn": 1852.0 / 3600.0, "mph": 0.44704}
_LENGTH_TO_M = {"m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001, "ft": 0.3048, "inch": 0.0254, "NM": 1852.0}
_IDENTITY = {("%", "percent"), ("°", "deg"), ("mm", "mm/h"), ("cm", "cm/h"), ("wmo code", "wmo_code")}
_TEMPERATURE_ALIASES = {"°C": "degC", "°F": "degF"}

# The unit each data-source unit is converted to before evaluation. An hourly accumulation in mm or cm is read
# as a rate over that hour.
CANONICAL_UNIT = {
    "km/h": "m/s", "m/s": "m/s", "kn": "m/s", "mph": "m/s",
    "°C": "degC", "°F": "degC",
    "mm": "mm/h", "inch": "mm/h", "cm": "cm/h",
    "%": "percent", "°": "deg", "m": "m", "ft": "m", "km": "m",
    "J/kg": "J/kg", "hPa": "hPa", "wmo code": "wmo_code",
}


def canonical_unit(source_unit: str) -> str:
    """The evaluation unit for a data-source unit. An unknown unit is an error, never a pass-through."""
    try:
        return CANONICAL_UNIT[source_unit]
    except KeyError:
        raise WeatherDataError(f"no conversion is defined for the source unit {source_unit!r}") from None


def convert(value: float, source_unit: str, target_unit: str) -> float:
    """Convert one value. Raises WeatherDataError if the pair of units is not known."""
    source = _TEMPERATURE_ALIASES.get(source_unit, source_unit)
    target = _TEMPERATURE_ALIASES.get(target_unit, target_unit)
    if source == target or (source_unit, target_unit) in _IDENTITY:
        return float(value)
    if source in _SPEED_TO_MS and target in _SPEED_TO_MS:
        return value * _SPEED_TO_MS[source] / _SPEED_TO_MS[target]
    if source in _LENGTH_TO_M and target in _LENGTH_TO_M:
        return value * _LENGTH_TO_M[source] / _LENGTH_TO_M[target]
    if (source, target) == ("degF", "degC"):
        return (value - 32.0) * 5.0 / 9.0
    if (source, target) == ("degC", "degF"):
        return value * 9.0 / 5.0 + 32.0
    if (source, target) == ("inch", "mm/h"):
        return value * 25.4
    raise WeatherDataError(f"no conversion is defined from {source_unit!r} to {target_unit!r}")
