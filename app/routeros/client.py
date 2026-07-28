"""Async RouterOS REST client.

One shared HTTPX AsyncClient (connection pool) per application, HTTP Basic
authentication, bounded timeouts and a concurrency semaphore so the router
is never flooded by parallel requests.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any

import httpx

log = logging.getLogger(__name__)


class RouterOSError(Exception):
    """Base error for RouterOS communication problems."""


class RouterOSAuthError(RouterOSError):
    """Authentication with the router failed."""


class RouterOSUnavailable(RouterOSError):
    """The router could not be reached or timed out."""


class RouterOSClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        ca_file: str = "",
        insecure_tls: bool = False,
        timeout: float = 10.0,
        max_concurrent: int = 3,
    ) -> None:
        verify: ssl.SSLContext | bool
        if insecure_tls:
            verify = False
        elif ca_file:
            verify = ssl.create_default_context(cafile=ca_file)
        else:
            verify = True
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/rest",
            auth=(username, password),
            verify=verify,
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
        )
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def close(self) -> None:
        await self._client.aclose()

    async def get(self, path: str, proplist: list[str] | None = None) -> Any:
        """GET a RouterOS REST resource, optionally limited via .proplist."""
        params = {".proplist": ",".join(proplist)} if proplist else None
        return await self._request("GET", path, params=params)

    async def post(self, path: str, payload: dict[str, Any]) -> Any:
        """POST a bounded RouterOS command (e.g. monitor-traffic with once)."""
        return await self._request("POST", path, json=payload)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with self._semaphore:
            try:
                response = await self._client.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                raise RouterOSUnavailable(f"{method} {path}: {exc}") from exc
            except httpx.HTTPError as exc:
                raise RouterOSError(f"{method} {path}: {exc}") from exc
        if response.status_code == 401:
            raise RouterOSAuthError("RouterOS rejected the configured credentials")
        if response.status_code >= 400:
            raise RouterOSError(f"{method} {path}: HTTP {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError as exc:
            raise RouterOSError(f"{method} {path}: invalid JSON in response") from exc
