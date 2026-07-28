"""Typed fetch + normalize helpers for the RouterOS resources Phase A uses."""

from __future__ import annotations

from typing import Any

from . import parsers
from .client import RouterOSClient

INTERFACE_PROPLIST = [
    "name", "type", "running", "disabled", "comment", "mtu",
    "rx-byte", "tx-byte", "rx-packet", "tx-packet",
    "rx-error", "tx-error", "rx-drop", "tx-drop", "link-downs",
]


async def fetch_system_resource(client: RouterOSClient) -> dict[str, Any]:
    raw = await client.get("/system/resource")
    return {
        "board_name": raw.get("board-name"),
        "version": raw.get("version"),
        "architecture": raw.get("architecture-name"),
        "cpu": raw.get("cpu"),
        "cpu_count": parsers.parse_int(raw.get("cpu-count")),
        "cpu_frequency_mhz": parsers.parse_int(raw.get("cpu-frequency")),
        "cpu_load_percent": parsers.parse_percent(raw.get("cpu-load")),
        "uptime_seconds": parsers.parse_duration(raw.get("uptime")),
        "uptime_raw": raw.get("uptime"),
        "free_memory_bytes": parsers.parse_size(raw.get("free-memory")),
        "total_memory_bytes": parsers.parse_size(raw.get("total-memory")),
        "free_hdd_bytes": parsers.parse_size(raw.get("free-hdd-space")),
        "total_hdd_bytes": parsers.parse_size(raw.get("total-hdd-space")),
        "raw": raw,
    }


async def fetch_system_health(client: RouterOSClient) -> list[dict[str, Any]]:
    """Health sensors vary by model/version, so discover them dynamically."""
    raw = await client.get("/system/health")
    if isinstance(raw, dict):  # older RouterOS returns a single object
        raw = [
            {"name": key, "value": value, "type": ""}
            for key, value in raw.items()
            if not key.startswith(".")
        ]
    sensors = []
    for item in raw:
        name = item.get("name", "")
        value = item.get("value")
        sensor_type = item.get("type", "")
        normalized: float | None
        if sensor_type in ("C", "temperature") or "temp" in name:
            normalized = parsers.parse_temperature(value)
            unit = "C"
        else:
            normalized = parsers.parse_float(value)
            unit = sensor_type
        sensors.append({
            "name": name,
            "raw_value": value,
            "raw_type": sensor_type,
            "value": normalized,
            "unit": unit,
            "parser_version": parsers.PARSER_VERSION,
        })
    return sensors


async def fetch_interfaces(client: RouterOSClient) -> list[dict[str, Any]]:
    raw = await client.get("/interface", proplist=INTERFACE_PROPLIST)
    interfaces = []
    for item in raw:
        interfaces.append({
            "name": item.get("name"),
            "type": item.get("type"),
            "comment": item.get("comment", ""),
            "running": parsers.parse_bool(item.get("running")),
            "disabled": parsers.parse_bool(item.get("disabled")),
            "mtu": parsers.parse_int(item.get("mtu")),
            "rx_bytes": parsers.parse_int(item.get("rx-byte")),
            "tx_bytes": parsers.parse_int(item.get("tx-byte")),
            "rx_packets": parsers.parse_int(item.get("rx-packet")),
            "tx_packets": parsers.parse_int(item.get("tx-packet")),
            "rx_errors": parsers.parse_int(item.get("rx-error")),
            "tx_errors": parsers.parse_int(item.get("tx-error")),
            "rx_drops": parsers.parse_int(item.get("rx-drop")),
            "tx_drops": parsers.parse_int(item.get("tx-drop")),
            "link_downs": parsers.parse_int(item.get("link-downs")),
        })
    return interfaces


async def fetch_identity(client: RouterOSClient) -> str:
    raw = await client.get("/system/identity")
    return raw.get("name", "") if isinstance(raw, dict) else ""
