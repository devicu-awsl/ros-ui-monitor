"""Browser-facing API. Exposes application data only - never generic
RouterOS proxying and never RouterOS credentials."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import __version__

router = APIRouter()

_SSE_KEEPALIVE_SECONDS = 20


@router.get("/api/v1/info")
async def info(request: Request) -> dict:
    """Static facts the dashboard header needs. No secrets."""
    settings = request.app.state.settings
    return {
        "version": __version__,
        "router_host": settings.router_host,
        "lan_mode": settings.lan_mode,
        "auth_enabled": settings.auth_enabled,
    }


@router.get("/api/v1/status")
async def status(request: Request) -> dict:
    state = request.app.state.cache
    return state.snapshot()


@router.get("/api/v1/interfaces")
async def interfaces(request: Request) -> dict:
    entry = request.app.state.cache.get("interfaces")
    if entry is None:
        return {"data": [], "updated_at": None, "age_seconds": None}
    return entry


@router.get("/api/v1/interfaces/{name}/history")
async def interface_history(request: Request, name: str, hours: float = Query(1.0, ge=0.05, le=72)) -> dict:
    db = request.app.state.db
    since = time.time() - hours * 3600
    rows = await asyncio.to_thread(db.interface_history, name, since)
    return {"name": name, "since": since, "samples": rows}


@router.get("/api/v1/device/history")
async def device_history(request: Request, hours: float = Query(1.0, ge=0.05, le=72)) -> dict:
    db = request.app.state.db
    since = time.time() - hours * 3600
    rows = await asyncio.to_thread(db.device_history, since)
    return {"since": since, "samples": rows}


@router.get("/api/v1/events")
async def events(request: Request, limit: int = Query(100, ge=1, le=1000)) -> dict:
    db = request.app.state.db
    rows = await asyncio.to_thread(db.recent_events, limit)
    return {"events": rows}


@router.get("/api/v1/health")
async def health_sensors(request: Request) -> dict:
    entry = request.app.state.cache.get("health")
    if entry is None:
        return {"data": [], "updated_at": None, "age_seconds": None}
    return entry


@router.get("/api/v1/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events: pushes each refreshed state group to the browser."""
    cache = request.app.state.cache

    async def event_source():
        queue = cache.subscribe()
        try:
            # initial full snapshot so a new client renders immediately
            yield f"event: snapshot\ndata: {json.dumps(cache.snapshot(), default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
                    yield f"event: update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            cache.unsubscribe(queue)

    return StreamingResponse(event_source(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict:
    ready = getattr(request.app.state, "ready", False)
    if not ready:
        raise HTTPException(status_code=503, detail="starting")
    return {"status": "ready"}
