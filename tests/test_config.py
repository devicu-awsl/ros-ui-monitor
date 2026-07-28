import pytest

from app.config import ConfigError, load_settings


def test_defaults():
    s = load_settings(env={})
    assert s.router_host == "192.168.88.1"
    assert s.router_api_port == 8728
    assert s.router_api_ssl_port == 8729
    assert s.router_url == "https://192.168.88.1"
    assert s.bind_host == "127.0.0.1"
    assert s.bind_port == 8000


def test_env_overrides():
    s = load_settings(env={
        "RBMON_ROUTER_URL": "https://10.0.0.1",
        "RBMON_BIND_PORT": "9000",
        "RBMON_ROUTER_INSECURE_TLS": "true",
    })
    assert s.router_url == "https://10.0.0.1"
    assert s.bind_port == 9000
    assert s.router_insecure_tls is True


def test_config_file(tmp_path):
    cfg = tmp_path / "config.env"
    cfg.write_text("RBMON_BIND_PORT=8123\n# comment\nRBMON_ROUTER_USERNAME=rbmon\n")
    s = load_settings(config_file=str(cfg), env={})
    assert s.bind_port == 8123
    assert s.router_username == "rbmon"


def test_env_wins_over_file(tmp_path):
    cfg = tmp_path / "config.env"
    cfg.write_text("RBMON_BIND_PORT=8123\n")
    s = load_settings(config_file=str(cfg), env={"RBMON_BIND_PORT": "8999"})
    assert s.bind_port == 8999


def test_invalid_url():
    with pytest.raises(ConfigError):
        load_settings(env={"RBMON_ROUTER_URL": "ftp://192.168.88.1"})


def test_invalid_port():
    with pytest.raises(ConfigError):
        load_settings(env={"RBMON_BIND_PORT": "99999"})


def test_missing_config_file():
    with pytest.raises(ConfigError):
        load_settings(config_file="/nonexistent/config.env", env={})
