"""In-memory current-state cache and SSE publish/subscribe bus.

Browsers are always served from this cache; they never trigger RouterOS
requests directly. Every group records when it was last refreshed so the
UI can show stale-data age instead of pretending old data is live.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any


class StateCache:
    def __init__(self) -> None:
        self._groups: dict[str, dict[str, Any]] = {}
        self._subscribers: set[asyncio.Queue[str]] = set()
        self.router_reachable: bool = False
        self.last_error: str | None = None

    def update(self, group: str, data: Any) -> None:
        self._groups[group] = {"data": data, "updated_at": time.time()}
        self._publish({"group": group, "data": data, "updated_at": self._groups[group]["updated_at"]})

    def get(self, group: str) -> dict[str, Any] | None:
        entry = self._groups.get(group)
        if entry is None:
            return None
        return {
            "data": entry["data"],
            "updated_at": entry["updated_at"],
            "age_seconds": round(time.time() - entry["updated_at"], 1),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "router_reachable": self.router_reachable,
            "last_error": self.last_error,
            "groups": {name: self.get(name) for name in self._groups},
        }

    def set_reachable(self, reachable: bool, error: str | None = None) -> None:
        changed = reachable != self.router_reachable or error != self.last_error
        self.router_reachable = reachable
        self.last_error = error
        if changed:
            self._publish({"group": "connectivity", "data": {"reachable": reachable, "error": error}})

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def _publish(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, default=str)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Slow client: drop it rather than blocking the collectors.
                self._subscribers.discard(queue)
