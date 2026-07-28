"""Local dashboard authentication for Phase B (LAN mode).

This protects the dashboard itself; it has nothing to do with the RouterOS
credentials, which never leave the application host. Everything here uses
the standard library so the PyInstaller bundle gains no dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
_SALT_BYTES = 16


def hash_password(password: str, salt: bytes | None = None,
                  iterations: int = PBKDF2_ITERATIONS) -> str:
    """Return an encoded hash: pbkdf2_sha256$iterations$salt_hex$hash_hex."""
    if salt is None:
        salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PBKDF2_ALGORITHM}${iterations}${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """Constant-time check of a password against an encoded hash."""
    try:
        algorithm, iterations, salt_hex, hash_hex = encoded.split("$")
        if algorithm != PBKDF2_ALGORITHM:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), hash_hex)


class SessionStore:
    """In-memory session tokens. Sessions do not survive a restart, which is
    the right trade-off for a single-user LAN appliance."""

    def __init__(self, lifetime_seconds: float) -> None:
        self._lifetime = lifetime_seconds
        self._sessions: dict[str, float] = {}  # token -> expiry

    def create(self) -> str:
        self._purge()
        token = secrets.token_urlsafe(32)
        self._sessions[token] = time.time() + self._lifetime
        return token

    def is_valid(self, token: str | None) -> bool:
        if not token:
            return False
        expiry = self._sessions.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            self._sessions.pop(token, None)
            return False
        return True

    def revoke(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def _purge(self) -> None:
        now = time.time()
        for token in [t for t, expiry in self._sessions.items() if expiry < now]:
            self._sessions.pop(token, None)


class LoginRateLimiter:
    """Throttles failed logins per client address so a tablet left on the LAN
    cannot be brute-forced."""

    def __init__(self, max_attempts: int = 5, window_seconds: float = 300.0) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._failures: dict[str, list[float]] = {}

    def is_blocked(self, client: str) -> bool:
        return len(self._recent(client)) >= self._max_attempts

    def record_failure(self, client: str) -> None:
        self._failures.setdefault(client, []).append(time.time())

    def reset(self, client: str) -> None:
        self._failures.pop(client, None)

    def retry_after(self, client: str) -> int:
        recent = self._recent(client)
        if len(recent) < self._max_attempts:
            return 0
        return max(1, int(recent[0] + self._window - time.time()))

    def _recent(self, client: str) -> list[float]:
        cutoff = time.time() - self._window
        recent = [t for t in self._failures.get(client, []) if t >= cutoff]
        if recent:
            self._failures[client] = recent
        else:
            self._failures.pop(client, None)
        return recent
