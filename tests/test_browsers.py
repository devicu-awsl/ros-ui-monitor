"""Browser discovery and ordering (no GUI toolkit required)."""

import app.browsers as browsers
from app.browsers import Browser, find_browsers


def test_detects_browsers_on_path(tmp_path, monkeypatch):
    fake = tmp_path / "firefox"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(browsers.os, "name", "posix")
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setenv("PATH", str(tmp_path))

    found = find_browsers()
    assert [b.name for b in found] == ["Mozilla Firefox"]
    assert found[0].command == str(fake)


def test_no_browsers_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(browsers.os, "name", "posix")
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_browsers() == []


def test_default_browser_sorts_first(monkeypatch):
    unordered = [
        Browser("Mozilla Firefox", "/x/firefox"),
        Browser("Brave", "/x/brave", is_default=True),
        Browser("Google Chrome", "/x/chrome"),
    ]
    monkeypatch.setattr(browsers, "_linux_browsers", lambda: unordered)
    monkeypatch.setattr(browsers.os, "name", "posix")
    monkeypatch.setattr(browsers.sys, "platform", "linux")

    names = [b.name for b in find_browsers()]
    assert names[0] == "Brave"                      # default is promoted
    assert names[1:] == ["Google Chrome", "Mozilla Firefox"]  # then familiar order


def test_launch_detaches_and_passes_url(monkeypatch):
    calls = {}

    def fake_popen(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(browsers.os, "name", "posix")
    monkeypatch.setattr(browsers.sys, "platform", "linux")
    monkeypatch.setattr(browsers.subprocess, "Popen", fake_popen)

    Browser("Mozilla Firefox", "/x/firefox").launch("http://127.0.0.1:8000/")
    assert calls["cmd"] == ["/x/firefox", "http://127.0.0.1:8000/"]
    # Detached, so closing the monitor never takes the browser down with it.
    assert calls["kwargs"]["start_new_session"] is True


def test_launch_uses_open_on_macos(monkeypatch):
    calls = {}
    monkeypatch.setattr(browsers.sys, "platform", "darwin")
    monkeypatch.setattr(browsers.subprocess, "Popen", lambda cmd, **kw: calls.update(cmd=cmd))

    Browser("Safari", "/Applications/Safari.app").launch("http://127.0.0.1:8000/")
    assert calls["cmd"] == ["open", "-a", "/Applications/Safari.app", "http://127.0.0.1:8000/"]
