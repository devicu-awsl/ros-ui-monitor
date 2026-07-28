"""Phase A collector jobs: system resource, health sensors, interfaces.

Interface throughput rates are derived from byte-counter deltas between
polls, which avoids running `monitor-traffic` continuously.
"""

from __future__ import annotations

import time
from typing import Any

from ..database.db import Database
from ..routeros import resources
from ..routeros.client import RouterOSClient
from ..state import StateCache


class Collectors:
    def __init__(self, client: RouterOSClient, state: StateCache, db: Database) -> None:
        self._client = client
        self._state = state
        self._db = db
        self._prev_counters: dict[str, tuple[float, int, int]] = {}  # name -> (ts, rx_bytes, tx_bytes)
        self._prev_running: dict[str, bool | None] = {}
        self._identity_fetched = False

    async def collect_resource(self) -> None:
        data = await resources.fetch_system_resource(self._client)
        if not self._identity_fetched:
            try:
                data["identity"] = await resources.fetch_identity(self._client)
                self._identity_fetched = True
            except Exception:
                data["identity"] = ""
        else:
            cached = self._state.get("resource")
            data["identity"] = (cached or {}).get("data", {}).get("identity", "")
        self._state.update("resource", data)
        health = self._state.get("health")
        temperature = None
        if health:
            for sensor in health["data"]:
                if sensor.get("unit") == "C" and sensor.get("value") is not None:
                    temperature = sensor["value"]
                    break
        await self._db.a_add_device_sample(
            data["cpu_load_percent"], data["free_memory_bytes"], data["total_memory_bytes"],
            data["uptime_seconds"], temperature,
        )

    async def collect_health(self) -> None:
        sensors = await resources.fetch_system_health(self._client)
        self._state.update("health", sensors)

    async def collect_interfaces(self) -> None:
        interfaces = await resources.fetch_interfaces(self._client)
        now = time.time()
        samples: list[dict[str, Any]] = []
        for iface in interfaces:
            name = iface["name"]
            rx, tx = iface.get("rx_bytes"), iface.get("tx_bytes")
            prev = self._prev_counters.get(name)
            rx_rate = tx_rate = None
            if prev is not None and rx is not None and tx is not None:
                prev_ts, prev_rx, prev_tx = prev
                dt = now - prev_ts
                # negative delta means counter reset or router reboot
                if dt > 0 and rx >= prev_rx and tx >= prev_tx:
                    rx_rate = (rx - prev_rx) * 8 / dt
                    tx_rate = (tx - prev_tx) * 8 / dt
                elif rx < prev_rx or tx < prev_tx:
                    await self._db.a_add_event(
                        "info", "interfaces", f"Counter reset detected on {name} (reboot or reset)")
            if rx is not None and tx is not None:
                self._prev_counters[name] = (now, rx, tx)
            iface["rx_rate_bps"] = rx_rate
            iface["tx_rate_bps"] = tx_rate
            samples.append(iface)

            prev_running = self._prev_running.get(name)
            if prev_running is not None and prev_running != iface["running"]:
                level = "info" if iface["running"] else "warning"
                verb = "up" if iface["running"] else "down"
                await self._db.a_add_event(level, "interfaces", f"Interface {name} went {verb}")
            self._prev_running[name] = iface["running"]

        self._state.update("interfaces", interfaces)
        await self._db.a_add_interface_samples(samples)
