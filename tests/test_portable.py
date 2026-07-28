"""Portable mode: config.env and the database beside the executable."""

import app.config as config
from app.config import (
    CONFIG_FILENAME,
    find_config_file,
    is_portable_config,
    load_settings,
)


def _fake_exe_dir(monkeypatch, path):
    monkeypatch.setattr(config, "exe_dir", lambda: path)


def _fake_program_data(monkeypatch, path):
    monkeypatch.setattr(config, "_default_data_dir", lambda: path)


def test_config_beside_exe_is_found(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    (exe / CONFIG_FILENAME).write_text("RBMON_BIND_PORT=8111\n")
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, tmp_path / "programdata")

    found = find_config_file(env={})
    assert found == exe / CONFIG_FILENAME
    assert is_portable_config(found)


def test_config_beside_exe_switches_data_dir(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    (exe / CONFIG_FILENAME).write_text("RBMON_BIND_PORT=8111\n")
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, tmp_path / "programdata")

    settings = load_settings(env={})
    assert settings.data_dir == exe
    assert settings.db_path == exe / "monitor.db"
    assert settings.bind_port == 8111  # the beside-exe config was actually read


def test_portable_flag_without_config_file(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, tmp_path / "programdata")

    assert load_settings(env={}, portable=True).data_dir == exe


def test_defaults_to_program_data(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    program_data = tmp_path / "programdata"
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, program_data)

    assert find_config_file(env={}) is None
    assert load_settings(env={}).data_dir == program_data


def test_program_data_config_is_not_portable(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    program_data = tmp_path / "programdata"
    program_data.mkdir()
    (program_data / CONFIG_FILENAME).write_text("RBMON_BIND_PORT=8222\n")
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, program_data)

    found = find_config_file(env={})
    assert found == program_data / CONFIG_FILENAME
    assert not is_portable_config(found)
    settings = load_settings(env={})
    assert settings.data_dir == program_data
    assert settings.bind_port == 8222


def test_explicit_config_wins_over_beside_exe(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    (exe / CONFIG_FILENAME).write_text("RBMON_BIND_PORT=8111\n")
    explicit = tmp_path / "custom.env"
    explicit.write_text("RBMON_BIND_PORT=8333\n")
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, tmp_path / "programdata")

    settings = load_settings(config_file=str(explicit), env={})
    assert settings.bind_port == 8333


def test_data_dir_env_overrides_portable(tmp_path, monkeypatch):
    exe = tmp_path / "app_dir"
    exe.mkdir()
    (exe / CONFIG_FILENAME).write_text("RBMON_BIND_PORT=8111\n")
    elsewhere = tmp_path / "elsewhere"
    _fake_exe_dir(monkeypatch, exe)
    _fake_program_data(monkeypatch, tmp_path / "programdata")

    settings = load_settings(env={"RBMON_DATA_DIR": str(elsewhere)})
    assert settings.data_dir == elsewhere
