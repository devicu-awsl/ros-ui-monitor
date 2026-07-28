"""Collector scheduler.

One asyncio task per metric group. Each loop:
  - never overlaps itself (sequential awaits inside one task);
  - adds small timing jitter so groups do not hit the router simultaneously;
  - applies exponential backoff while the router is unreachable;
  - records connectivity transitions as events.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable

from ..database.db import Database
from ..routeros.client import RouterOSAuthError, RouterOSError, RouterOSUnavailable
from ..state import StateCache

log = logging.getLogger(__name__)

CollectorFn = Callable[[], Awaitable[None]]


class Scheduler:
    def __init__(self, state: StateCache, db: Database) -> None:
        self._state = state
        self._db = db
        self._tasks: list[asyncio.Task[None]] = []
        self._was_reachable: bool | None = None

    def add_job(self, name: str, interval: float, fn: CollectorFn) -> None:
        self._tasks.append(asyncio.create_task(self._run_loop(name, interval, fn), name=f"collector:{name}"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run_loop(self, name: str, interval: float, fn: CollectorFn) -> None:
        backoff = interval
        await asyncio.sleep(random.uniform(0, min(interval, 2.0)))  # startup jitter
        while True:
            try:
                await fn()
            except RouterOSAuthError as exc:
                await self._on_failure(name, f"authentication failed: {exc}")
                backoff = min(backoff * 2, 300.0)
                await asyncio.sleep(backoff)
                continue
            except RouterOSUnavailable as exc:
                await self._on_failure(name, str(exc))
                backoff = min(backoff * 2, 120.0)
                await asyncio.sleep(backoff)
                continue
            except RouterOSError as exc:
                await self._on_failure(name, str(exc))
                await asyncio.sleep(interval)
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("collector %s crashed; continuing", name)
                await asyncio.sleep(interval)
                continue
            await self._on_success(name)
            backoff = interval
            await asyncio.sleep(interval + random.uniform(0, interval * 0.1))

    async def _on_success(self, name: str) -> None:
        if self._was_reachable is not True:
            self._was_reachable = True
            self._state.set_reachable(True)
            await self._db.a_add_event("info", "collector", "Router connection established")

    async def _on_failure(self, name: str, error: str) -> None:
        log.warning("collector %s failed: %s", name, error)
        if self._was_reachable is not False:
            self._was_reachable = False
            self._state.set_reachable(False, error)
            await self._db.a_add_event("warning", "collector", f"Router unreachable ({name})", {"error": error})
