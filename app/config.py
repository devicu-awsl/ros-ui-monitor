"""Application configuration.

Configuration comes from (lowest to highest precedence):
  1. Built-in defaults
  2. An optional .env-style config file (RBMON_CONFIG or --config)
  3. Process environment variables
  4. Command-line arguments

RB5009 assumptions for Phase A:
  - Router address: 192.168.88.1
  - RouterOS API service ports: TCP 8728 (api) and 8729 (api-ssl, secure)
  - RouterOS REST API is served by the www-ssl service (HTTPS). The REST
    base URL is configurable; the API ports are recorded so the UI can show
    the expected service layout and future adapters can use them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


def _default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "RB5009Monitor"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "rb5009-monitor"


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


def load_settings(config_file: str | None = None, env: dict[str, str] | None = None) -> Settings:
    env = dict(env if env is not None else os.environ)
    file_path = config_file or env.get("RBMON_CONFIG")
    if file_path:
        p = Path(file_path)
        if not p.is_file():
            raise ConfigError(f"Config file not found: {p}")
        merged = _parse_env_file(p)
        merged.update(env)  # process env wins over file
        env = merged

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
        data_dir=Path(get("RBMON_DATA_DIR", str(_default_data_dir()))),
        poll_resource=float(get("RBMON_POLL_RESOURCE", "5")),
        poll_health=float(get("RBMON_POLL_HEALTH", "15")),
        poll_interfaces=float(get("RBMON_POLL_INTERFACES", "3")),
        max_concurrent_requests=int(get("RBMON_MAX_CONCURRENT", "3")),
        retention_hours=int(get("RBMON_RETENTION_HOURS", "72")),
        log_level=get("RBMON_LOG_LEVEL", "INFO").upper(),
    )
    s.validate()
    return s
