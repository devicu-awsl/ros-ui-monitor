"""Application configuration.

Configuration comes from (lowest to highest precedence):
  1. Built-in defaults
  2. An optional .env-style config file (RBMON_CONFIG or --config)
  3. Process environment variables
  4. Command-line arguments

RB5009 assumptions:
  - Router address: 192.168.88.1
  - RouterOS API service ports: TCP 8728 (api) and 8729 (api-ssl, secure)
  - RouterOS REST API is served by the www-ssl service (HTTPS). The REST
    base URL is configurable; the API ports are recorded so the UI can show
    the expected service layout.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = "config.env"


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


def exe_dir() -> Path:
    """Directory holding the running executable.

    For a PyInstaller one-file build this must come from sys.executable: the
    module files live in a temporary extraction directory that is deleted on
    exit, so __file__ would point somewhere useless for persistent data.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent  # project root when run from source


def _default_data_dir() -> Path:
    """Mutable data lives outside the PyInstaller bundle, which is temporary."""
    if os.name == "nt":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "RB5009Monitor"
    return Path.home() / ".rb5009-monitor"  # dev machines only; target is Windows


def find_config_file(explicit: str | None = None, env: dict[str, str] | None = None) -> Path | None:
    """Locate the configuration file, preferring the most explicit source.

    A config.env sitting next to the executable also switches the application
    into portable mode, so a folder holding the .exe and its config is
    self-contained and can live on a USB stick.
    """
    env = dict(env if env is not None else os.environ)
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        return path
    if env.get("RBMON_CONFIG"):
        path = Path(env["RBMON_CONFIG"])
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        return path
    for candidate in (exe_dir() / CONFIG_FILENAME, _default_data_dir() / CONFIG_FILENAME):
        if candidate.is_file():
            return candidate
    return None


def is_portable_config(config_path: Path | None) -> bool:
    """True when the config file sits beside the executable."""
    if config_path is None:
        return False
    try:
        return config_path.resolve().parent == exe_dir()
    except OSError:
        return False


@dataclass
class Settings:
    # RouterOS connection
    router_host: str = "192.168.88.1"
    router_api_port: int = 8728        # RouterOS API (plain)
    router_api_ssl_port: int = 8729    # RouterOS API (secure)
    router_url: str = "https://192.168.88.1"  # REST base URL (www-ssl)
    router_username: str = ""
    router_password: str = ""
    router_ca_file: str = ""
    router_insecure_tls: bool = False  # allow self-signed certs (LAN bootstrap only)
    router_timeout: float = 10.0       # well under the RouterOS 60 s REST limit

    # Web server
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000
    open_browser: bool = True

    # Dashboard authentication (Phase B / LAN mode).
    # Supply auth_password_hash (preferred, generate with --hash-password) or
    # auth_password; either one enables authentication.
    auth_username: str = "admin"
    auth_password: str = ""
    auth_password_hash: str = ""
    session_hours: float = 12.0
    login_max_attempts: int = 5
    login_window_seconds: float = 300.0

    # Storage
    data_dir: Path = field(default_factory=_default_data_dir)

    # Collector cadences (seconds)
    poll_resource: float = 5.0
    poll_health: float = 15.0
    poll_interfaces: float = 3.0
    max_concurrent_requests: int = 3

    # History retention
    retention_hours: int = 72

    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "monitor.db"

    @property
    def lan_mode(self) -> bool:
        return self.bind_host in ("0.0.0.0", "::")

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_password_hash or self.auth_password)

    def validate(self) -> None:
        if not self.router_url.startswith(("http://", "https://")):
            raise ConfigError(f"RBMON_ROUTER_URL must start with http:// or https:// (got {self.router_url!r})")
        if not (1 <= self.bind_port <= 65535):
            raise ConfigError(f"RBMON_BIND_PORT out of range: {self.bind_port}")
        for name in ("poll_resource", "poll_health", "poll_interfaces"):
            if getattr(self, name) < 1.0:
                raise ConfigError(f"{name} must be >= 1 second")
        if self.router_ca_file and not Path(self.router_ca_file).is_file():
            raise ConfigError(f"RBMON_ROUTER_CA_FILE not found: {self.router_ca_file}")
        if self.retention_hours < 1:
            raise ConfigError("RBMON_RETENTION_HOURS must be >= 1")
        if self.auth_enabled and not self.auth_username:
            raise ConfigError("RBMON_AUTH_USERNAME must not be empty when a password is set")
        if self.session_hours <= 0:
            raise ConfigError("RBMON_SESSION_HOURS must be > 0")


def _parse_env_file(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, # comments, blank lines ignored."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_BOOL_TRUE = {"1", "true", "yes", "on"}


def load_settings(config_file: str | None = None, env: dict[str, str] | None = None,
                  portable: bool = False) -> Settings:
    """Build Settings from the config file, environment and portable flag.

    Data directory precedence: RBMON_DATA_DIR, then the executable's own
    directory in portable mode, then the per-machine default
    (C:\\ProgramData\\RB5009Monitor on Windows).
    """
    env = dict(env if env is not None else os.environ)
    config_path = find_config_file(config_file, env)
    if config_path is not None:
        merged = _parse_env_file(config_path)
        merged.update(env)  # process env wins over file
        env = merged
    portable = portable or is_portable_config(config_path)

    def get(key: str, default: str) -> str:
        return env.get(key, default)

    def get_bool(key: str, default: bool) -> bool:
        raw = env.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in _BOOL_TRUE

    s = Settings(
        router_host=get("RBMON_ROUTER_HOST", "192.168.88.1"),
        router_api_port=int(get("RBMON_ROUTER_API_PORT", "8728")),
        router_api_ssl_port=int(get("RBMON_ROUTER_API_SSL_PORT", "8729")),
        router_url=get("RBMON_ROUTER_URL", f"https://{get('RBMON_ROUTER_HOST', '192.168.88.1')}"),
        router_username=get("RBMON_ROUTER_USERNAME", ""),
        router_password=get("RBMON_ROUTER_PASSWORD", ""),
        router_ca_file=get("RBMON_ROUTER_CA_FILE", ""),
        router_insecure_tls=get_bool("RBMON_ROUTER_INSECURE_TLS", False),
        router_timeout=float(get("RBMON_ROUTER_TIMEOUT", "10")),
        bind_host=get("RBMON_BIND_HOST", "127.0.0.1"),
        bind_port=int(get("RBMON_BIND_PORT", "8000")),
        auth_username=get("RBMON_AUTH_USERNAME", "admin"),
        auth_password=get("RBMON_AUTH_PASSWORD", ""),
        auth_password_hash=get("RBMON_AUTH_PASSWORD_HASH", ""),
        session_hours=float(get("RBMON_SESSION_HOURS", "12")),
        login_max_attempts=int(get("RBMON_LOGIN_MAX_ATTEMPTS", "5")),
        login_window_seconds=float(get("RBMON_LOGIN_WINDOW_SECONDS", "300")),
        data_dir=Path(get("RBMON_DATA_DIR", str(exe_dir() if portable else _default_data_dir()))),
        poll_resource=float(get("RBMON_POLL_RESOURCE", "5")),
        poll_health=float(get("RBMON_POLL_HEALTH", "15")),
        poll_interfaces=float(get("RBMON_POLL_INTERFACES", "3")),
        max_concurrent_requests=int(get("RBMON_MAX_CONCURRENT", "3")),
        retention_hours=int(get("RBMON_RETENTION_HOURS", "72")),
        log_level=get("RBMON_LOG_LEVEL", "INFO").upper(),
    )
    s.validate()
    return s
