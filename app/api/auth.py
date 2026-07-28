"""Login and logout for LAN mode.

Session cookies are HttpOnly and SameSite=Lax. The Secure flag is not set
because Phase B serves plain HTTP on the LAN; treat the dashboard password
as protection against casual access from other devices, not as a substitute
for a trusted network.

SameSite=Lax is also what protects the POST endpoints from cross-site
request forgery: the dashboard exposes no RouterOS write operations, so
login and logout are the only state-changing requests.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from ..security import verify_password

router = APIRouter()

SESSION_COOKIE = "rbmon_session"


class LoginRequest(BaseModel):
    username: str
    password: str


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@router.post("/api/v1/login")
async def login(request: Request, response: Response, body: LoginRequest) -> dict:
    settings = request.app.state.settings
    limiter = request.app.state.login_limiter
    client = client_key(request)

    if limiter.is_blocked(client):
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(limiter.retry_after(client))},
        )

    username_ok = _constant_time_equals(body.username, settings.auth_username)
    password_ok = verify_password(body.password, request.app.state.auth_password_hash)
    if not (username_ok and password_ok):
        limiter.record_failure(client)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    limiter.reset(client)
    token = request.app.state.sessions.create()
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", max_age=int(settings.session_hours * 3600), path="/",
    )
    return {"status": "ok"}


@router.post("/api/v1/logout")
async def logout(request: Request, response: Response) -> dict:
    request.app.state.sessions.revoke(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}
