"""End-to-end checks that LAN mode really is protected.

These use FastAPI's TestClient with the lifespan stubbed out, so they
exercise the middleware and login routes without any collector talking to a
router.
"""

import contextlib

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import hash_password

PASSWORD = "tablet-lan-password"
PROTECTED_API = [
    "/api/v1/status",
    "/api/v1/interfaces",
    "/api/v1/events",
    "/api/v1/health",
    "/api/v1/info",
]


@contextlib.asynccontextmanager
async def _noop_lifespan(app):
    app.state.ready = True
    yield


def _build_client(tmp_path, **overrides) -> TestClient:
    values = dict(
        bind_host="0.0.0.0",  # LAN mode
        data_dir=tmp_path,
        auth_username="admin",
        auth_password_hash=hash_password(PASSWORD, iterations=1000),
        open_browser=False,
    )
    values.update(overrides)
    app = create_app(Settings(**values))
    app.router.lifespan_context = _noop_lifespan
    return TestClient(app)


@pytest.fixture(name="client")
def client_fixture(tmp_path):
    with _build_client(tmp_path) as c:
        yield c


@pytest.fixture(name="open_client")
def open_client_fixture(tmp_path):
    """LAN mode with no password configured: authentication is off."""
    with _build_client(tmp_path, auth_password_hash="", auth_password="") as c:
        yield c


@pytest.mark.parametrize("path", PROTECTED_API)
def test_api_requires_authentication(client, path):
    assert client.get(path).status_code == 401


def test_dashboard_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_probes_and_login_page_are_public(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    assert client.get("/login").status_code == 200
    assert client.get("/static/css/style.css").status_code == 200


def test_login_rejects_bad_password(client):
    assert client.post("/api/v1/login",
                       json={"username": "admin", "password": "wrong"}).status_code == 401


def test_login_rejects_bad_username(client):
    assert client.post("/api/v1/login",
                       json={"username": "root", "password": PASSWORD}).status_code == 401


def test_login_grants_access_then_logout_revokes(client):
    assert client.post("/api/v1/login",
                       json={"username": "admin", "password": PASSWORD}).status_code == 200
    assert client.get("/api/v1/info").status_code == 200

    assert client.post("/api/v1/logout").status_code == 200
    assert client.get("/api/v1/info").status_code == 401


def test_session_cookie_is_httponly(client):
    resp = client.post("/api/v1/login", json={"username": "admin", "password": PASSWORD})
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert PASSWORD not in set_cookie


def test_repeated_failures_are_rate_limited(client):
    for _ in range(5):
        client.post("/api/v1/login", json={"username": "admin", "password": "wrong"})
    blocked = client.post("/api/v1/login", json={"username": "admin", "password": "wrong"})
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    # Correct credentials stay blocked while the limiter window is open.
    assert client.post("/api/v1/login",
                       json={"username": "admin", "password": PASSWORD}).status_code == 429


def test_no_password_configured_leaves_dashboard_open(open_client):
    assert open_client.get("/api/v1/info").status_code == 200
    assert open_client.get("/", follow_redirects=False).status_code == 200
