import time

from app.security import (
    LoginRateLimiter,
    SessionStore,
    hash_password,
    verify_password,
)

# Keep test hashing cheap; production uses the module default.
FAST_ITERATIONS = 1000


def test_hash_round_trip():
    encoded = hash_password("correct horse", iterations=FAST_ITERATIONS)
    assert verify_password("correct horse", encoded)
    assert not verify_password("wrong horse", encoded)


def test_hash_is_salted():
    a = hash_password("same", iterations=FAST_ITERATIONS)
    b = hash_password("same", iterations=FAST_ITERATIONS)
    assert a != b
    assert verify_password("same", a) and verify_password("same", b)


def test_password_never_stored_in_clear():
    encoded = hash_password("supersecret", iterations=FAST_ITERATIONS)
    assert "supersecret" not in encoded


def test_verify_rejects_malformed_hash():
    assert not verify_password("x", "")
    assert not verify_password("x", "garbage")
    assert not verify_password("x", "md5$1$aa$bb")


def test_session_lifecycle():
    store = SessionStore(lifetime_seconds=60)
    token = store.create()
    assert store.is_valid(token)
    store.revoke(token)
    assert not store.is_valid(token)


def test_session_rejects_unknown_and_empty():
    store = SessionStore(lifetime_seconds=60)
    assert not store.is_valid(None)
    assert not store.is_valid("")
    assert not store.is_valid("not-a-real-token")


def test_session_expires():
    store = SessionStore(lifetime_seconds=-1)  # already expired on creation
    assert not store.is_valid(store.create())


def test_rate_limiter_blocks_after_max_attempts():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(2):
        limiter.record_failure("10.0.0.5")
    assert not limiter.is_blocked("10.0.0.5")
    limiter.record_failure("10.0.0.5")
    assert limiter.is_blocked("10.0.0.5")
    assert limiter.retry_after("10.0.0.5") > 0


def test_rate_limiter_is_per_client():
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
    limiter.record_failure("10.0.0.5")
    assert limiter.is_blocked("10.0.0.5")
    assert not limiter.is_blocked("10.0.0.6")


def test_rate_limiter_window_expires():
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=0.05)
    limiter.record_failure("10.0.0.5")
    assert limiter.is_blocked("10.0.0.5")
    time.sleep(0.06)
    assert not limiter.is_blocked("10.0.0.5")


def test_successful_login_resets_failures():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("10.0.0.5")
    limiter.reset("10.0.0.5")
    limiter.record_failure("10.0.0.5")
    assert not limiter.is_blocked("10.0.0.5")
