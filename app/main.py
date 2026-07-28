"""Application entry point.

Phase A (localhost) and Phase B (LAN) are the same PyInstaller executable;
only the bind address and authentication differ:

    rb5009-monitor.exe                       # Phase A: 127.0.0.1 only
    rb5009-monitor.exe --lan                 # Phase B: all interfaces
    rb5009-monitor.exe --host 0.0.0.0 --port 8000
    rb5009-monitor.exe --no-browser
    rb5009-monitor.exe --config "C:\\ProgramData\\RB5009Monitor\\config.env"
    rb5009-monitor.exe --hash-password       # make a password hash for config
"""

from __future__ import annotations

import argparse
import getpass
import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.auth import SESSION_COOKIE, router as auth_router
from .api.routes import router as api_router
from .config import ConfigError, Settings, load_settings
from .lifespan import lifespan
from .security import LoginRateLimiter, SessionStore, hash_password

log = logging.getLogger(__name__)

# Reachable without a session: the login page itself, the assets it needs,
# and the probes, which reveal nothing beyond whether the service is up.
# Everything else requires authentication.
_PUBLIC_PATHS = frozenset({"/login", "/api/v1/login", "/healthz", "/readyz"})
_PUBLIC_PREFIXES = ("/static/",)


def _static_dir() -> Path:
    """Locate bundled static files both in source and PyInstaller runs."""
    base = Path(getattr(sys, "_MEIPASS", "")) / "app" if getattr(sys, "_MEIPASS", None) else Path(__file__).parent
    return base / "static"


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="RB5009 Monitor", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.ready = False
    app.state.sessions = SessionStore(settings.session_hours * 3600)
    app.state.login_limiter = LoginRateLimiter(settings.login_max_attempts, settings.login_window_seconds)
    # Hash a plaintext password once at startup so it is never compared in clear.
    app.state.auth_password_hash = (
        settings.auth_password_hash or (hash_password(settings.auth_password) if settings.auth_password else "")
    )

    static = _static_dir()
    app.include_router(auth_router)
    app.include_router(api_router)
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    if settings.auth_enabled:
        @app.middleware("http")
        async def require_session(request: Request, call_next):
            path = request.url.path
            if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
                return await call_next(request)
            if app.state.sessions.is_valid(request.cookies.get(SESSION_COOKIE)):
                return await call_next(request)
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            return RedirectResponse("/login", status_code=303)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/login", include_in_schema=False)
    async def login_page() -> FileResponse:
        return FileResponse(static / "login.html")

    return app


def _lan_address() -> str:
    """Best-effort LAN IP of this PC, for the Phase B tablet/phone URL."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.88.1", 1))  # no packets sent; just picks the route
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "<this PC's LAN address>"


def _open_browser_when_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    ready_url = url.rstrip("/") + "/readyz"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(ready_url, timeout=2) as resp:
                if resp.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            pass
        time.sleep(0.5)


def _hash_password_interactively() -> int:
    password = getpass.getpass("Dashboard password: ")
    if not password:
        print("No password entered.", file=sys.stderr)
        return 2
    if password != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 2
    print("\nAdd this line to your config.env:\n")
    print(f"RBMON_AUTH_PASSWORD_HASH={hash_password(password)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rb5009-monitor",
                                     description="LAN monitoring dashboard for a MikroTik RB5009")
    parser.add_argument("--host", help="bind address (default 127.0.0.1)")
    parser.add_argument("--lan", action="store_true",
                        help="Phase B LAN mode: bind all interfaces so tablets and phones can connect")
    parser.add_argument("--port", type=int, help="bind port (default 8000)")
    parser.add_argument("--config", help="path to a .env-style configuration file")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser on startup")
    parser.add_argument("--hash-password", action="store_true",
                        help="prompt for a dashboard password and print its hash, then exit")
    parser.add_argument("--version", action="version", version=f"rb5009-monitor {__version__}")
    args = parser.parse_args(argv)

    if args.hash_password:
        return _hash_password_interactively()

    try:
        settings = load_settings(config_file=args.config)
        if args.lan:
            settings.bind_host = "0.0.0.0"
        if args.host:
            settings.bind_host = args.host
        if args.port:
            settings.bind_port = args.port
        if args.no_browser:
            settings.open_browser = False
        settings.validate()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = create_app(settings)

    local_url = f"http://127.0.0.1:{settings.bind_port}/" if settings.lan_mode \
        else f"http://{settings.bind_host}:{settings.bind_port}/"
    if settings.lan_mode:
        log.info("LAN mode: other devices can connect at http://%s:%d/", _lan_address(), settings.bind_port)
        log.info("Allow rb5009-monitor through Windows Firewall on the private network if prompted.")
        if settings.auth_enabled:
            log.info("Dashboard authentication is enabled for user %r.", settings.auth_username)
        else:
            log.warning("LAN mode without a dashboard password: any device on the LAN can open the "
                        "dashboard. Set RBMON_AUTH_PASSWORD_HASH (see --hash-password) to require login.")

    if settings.open_browser:
        threading.Thread(target=_open_browser_when_ready, args=(local_url,), daemon=True).start()

    import uvicorn

    uvicorn.run(app, host=settings.bind_host, port=settings.bind_port,
                log_level=settings.log_level.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
