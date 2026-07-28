"""FastAPI application lifespan: wire up client, cache, database and
collectors on startup; shut everything down cleanly so SQLite is never
left mid-write."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .collectors.jobs import Collectors
from .collectors.scheduler import Scheduler
from .config import Settings
from .database.db import Database
from .routeros.client import RouterOSClient
from .state import StateCache

log = logging.getLogger(__name__)

_PRUNE_INTERVAL_SECONDS = 3600


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    cache = StateCache()
    db = Database(settings.db_path)
    client = RouterOSClient(
        settings.router_url,
        settings.router_username,
        settings.router_password,
        ca_file=settings.router_ca_file,
        insecure_tls=settings.router_insecure_tls,
        timeout=settings.router_timeout,
        max_concurrent=settings.max_concurrent_requests,
    )
    app.state.cache = cache
    app.state.db = db
    app.state.client = client

    collectors = Collectors(client, cache, db)
    scheduler = Scheduler(cache, db)
    scheduler.add_job("resource", settings.poll_resource, collectors.collect_resource)
    scheduler.add_job("health", settings.poll_health, collectors.collect_health)
    scheduler.add_job("interfaces", settings.poll_interfaces, collectors.collect_interfaces)

    async def prune_loop() -> None:
        while True:
            await asyncio.sleep(_PRUNE_INTERVAL_SECONDS)
            deleted = await db.a_prune(settings.retention_hours)
            if deleted:
                log.info("pruned %d old rows", deleted)

    prune_task = asyncio.create_task(prune_loop(), name="prune")
    app.state.ready = True
    log.info("rb5009-monitor started; router=%s data=%s", settings.router_url, settings.data_dir)
    try:
        yield
    finally:
        app.state.ready = False
        prune_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await prune_task
        await scheduler.stop()
        await client.close()
        db.close()
        log.info("rb5009-monitor stopped cleanly")
