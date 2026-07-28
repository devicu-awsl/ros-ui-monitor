"""Normalization of RouterOS REST string values.

RouterOS REST encodes every value as a string. These parsers convert them
into typed Python values; when parsing is uncertain the raw value is
preserved by the caller.
"""

from __future__ import annotations

import re

PARSER_VERSION = 1

_SIZE_UNITS = {
    "": 1,
    "b": 1,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
}

_RATE_UNITS = {
    "bps": 1,
    "kbps": 1_000,
    "mbps": 1_000_000,
    "gbps": 1_000_000_000,
}

_DURATION_RE = re.compile(r"(\d+)(ms|us|w|d|h|m|s)")
_DURATION_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1, "ms": 0.001, "us": 0.000001}


def parse_bool(value: str | bool | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("true", "yes"):
        return True
    if v in ("false", "no"):
        return False
    return None


def parse_int(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def parse_float(value: str | float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def parse_percent(value: str | None) -> float | None:
    """'23%' -> 23.0 ; '23' -> 23.0"""
    if value is None:
        return None
    v = str(value).strip().rstrip("%").strip()
    return parse_float(v)


def parse_size(value: str | None) -> int | None:
    """'94.2MiB' -> bytes. Plain numbers are already bytes."""
    if value is None:
        return None
    v = str(value).strip()
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([A-Za-z]*)", v)
    if not m:
        return None
    number, unit = m.group(1), m.group(2).lower()
    if unit not in _SIZE_UNITS:
        return None
    return int(float(number) * _SIZE_UNITS[unit])


def parse_duration(value: str | None) -> float | None:
    """'2d20h12m20s' -> seconds."""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    total = 0.0
    matched = False
    for amount, unit in _DURATION_RE.findall(v):
        total += int(amount) * _DURATION_SECONDS[unit]
        matched = True
    if not matched:
        return parse_float(v)
    return total


def parse_rate(value: str | None) -> int | None:
    """'100Mbps' or plain bps string -> bits per second."""
    if value is None:
        return None
    v = str(value).strip().lower()
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([a-z]*)", v)
    if not m:
        return None
    number, unit = m.group(1), m.group(2)
    if unit == "":
        return int(float(number))
    if unit in _RATE_UNITS:
        return int(float(number) * _RATE_UNITS[unit])
    return None


def parse_temperature(value: str | None) -> float | None:
    """'42C' / '42' -> 42.0 (Celsius)."""
    if value is None:
        return None
    v = str(value).strip().rstrip("Cc").strip()
    return parse_float(v)
