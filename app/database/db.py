"""SQLite history store (WAL mode).

Only this application writes the database. Writes come from the collector
loops via asyncio.to_thread so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS device_samples (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    cpu_load REAL,
    free_memory INTEGER,
    total_memory INTEGER,
    uptime_seconds REAL,
    temperature REAL
);
CREATE INDEX IF NOT EXISTS idx_device_samples_ts ON device_samples (ts);
CREATE TABLE IF NOT EXISTS interface_samples (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    name TEXT NOT NULL,
    running INTEGER,
    rx_bytes INTEGER,
    tx_bytes INTEGER,
    rx_rate_bps REAL,
    tx_rate_bps REAL,
    rx_errors INTEGER,
    tx_errors INTEGER,
    link_downs INTEGER
);
CREATE INDEX IF NOT EXISTS idx_interface_samples_ts ON interface_samples (name, ts);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
"""


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    # -- synchronous primitives (called via asyncio.to_thread) --------------

    def add_device_sample(self, cpu_load: float | None, free_memory: int | None,
                          total_memory: int | None, uptime_seconds: float | None,
                          temperature: float | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO device_samples (ts, cpu_load, free_memory, total_memory, uptime_seconds, temperature)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), cpu_load, free_memory, total_memory, uptime_seconds, temperature),
            )
            self._conn.commit()

    def add_interface_samples(self, samples: list[dict[str, Any]]) -> None:
        now = time.time()
        with self._lock:
            self._conn.executemany(
                "INSERT INTO interface_samples (ts, name, running, rx_bytes, tx_bytes, rx_rate_bps, tx_rate_bps,"
                " rx_errors, tx_errors, link_downs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (now, s["name"], 1 if s.get("running") else 0, s.get("rx_bytes"), s.get("tx_bytes"),
                     s.get("rx_rate_bps"), s.get("tx_rate_bps"), s.get("rx_errors"), s.get("tx_errors"),
                     s.get("link_downs"))
                    for s in samples
                ],
            )
            self._conn.commit()

    def add_event(self, level: str, source: str, message: str, details: Any = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, level, source, message, details) VALUES (?, ?, ?, ?, ?)",
                (time.time(), level, source, message, json.dumps(details, default=str) if details else None),
            )
            self._conn.commit()

    def device_history(self, since: float) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, cpu_load, free_memory, total_memory, temperature FROM device_samples"
                " WHERE ts >= ? ORDER BY ts", (since,),
            ).fetchall()
        return [dict(r) for r in rows]

    def interface_history(self, name: str, since: float) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, running, rx_rate_bps, tx_rate_bps, rx_errors, tx_errors, link_downs"
                " FROM interface_samples WHERE name = ? AND ts >= ? ORDER BY ts", (name, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, level, source, message, details FROM events ORDER BY ts DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def prune(self, retention_hours: int) -> int:
        cutoff = time.time() - retention_hours * 3600
        with self._lock:
            c1 = self._conn.execute("DELETE FROM device_samples WHERE ts < ?", (cutoff,)).rowcount
            c2 = self._conn.execute("DELETE FROM interface_samples WHERE ts < ?", (cutoff,)).rowcount
            # keep events three times longer than raw samples
            c3 = self._conn.execute(
                "DELETE FROM events WHERE ts < ?", (time.time() - retention_hours * 3 * 3600,)
            ).rowcount
            self._conn.commit()
        return c1 + c2 + c3

    # -- async wrappers ------------------------------------------------------

    async def a_add_device_sample(self, *args: Any) -> None:
        await asyncio.to_thread(self.add_device_sample, *args)

    async def a_add_interface_samples(self, samples: list[dict[str, Any]]) -> None:
        await asyncio.to_thread(self.add_interface_samples, samples)

    async def a_add_event(self, level: str, source: str, message: str, details: Any = None) -> None:
        await asyncio.to_thread(self.add_event, level, source, message, details)

    async def a_prune(self, retention_hours: int) -> int:
        return await asyncio.to_thread(self.prune, retention_hours)
