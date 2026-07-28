"""Discovery of the web browsers installed on this device.

Kept free of any GUI import so it can be tested, and used, without Qt.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Friendly names for the executables we look for on Windows and Linux.
_KNOWN_ORDER = [
    "Google Chrome", "Microsoft Edge", "Mozilla Firefox", "Brave", "Vivaldi",
    "Opera", "Chromium", "Safari",
]

_LINUX_CANDIDATES = [
    ("Google Chrome", ["google-chrome", "google-chrome-stable"]),
    ("Chromium", ["chromium", "chromium-browser"]),
    ("Mozilla Firefox", ["firefox", "firefox-esr"]),
    ("Microsoft Edge", ["microsoft-edge", "microsoft-edge-stable"]),
    ("Brave", ["brave-browser", "brave"]),
    ("Vivaldi", ["vivaldi", "vivaldi-stable"]),
    ("Opera", ["opera"]),
]

_MACOS_CANDIDATES = [
    ("Safari", "/Applications/Safari.app"),
    ("Google Chrome", "/Applications/Google Chrome.app"),
    ("Mozilla Firefox", "/Applications/Firefox.app"),
    ("Microsoft Edge", "/Applications/Microsoft Edge.app"),
    ("Brave", "/Applications/Brave Browser.app"),
]


@dataclass(frozen=True)
class Browser:
    name: str
    command: str          # executable path, or bundle path on macOS
    icon_path: str = ""   # file an icon can be extracted from, if known
    is_default: bool = False

    def launch(self, url: str) -> None:
        """Open url in this browser, detached so closing us never closes it."""
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", self.command, url])
        elif os.name == "nt":
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0)
                     | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            subprocess.Popen([self.command, url], close_fds=True, creationflags=flags)
        else:
            subprocess.Popen([self.command, url], close_fds=True, start_new_session=True)


def _windows_browsers() -> list[Browser]:
    """Read the browsers Windows itself advertises.

    HKEY_*\\SOFTWARE\\Clients\\StartMenuInternet is the documented registration
    point every mainstream Windows browser writes to, so this picks up
    browsers installed per-machine and per-user without hardcoding paths.
    """
    import winreg  # noqa: PLC0415 - Windows only

    found: dict[str, Browser] = {}
    default_name = ""
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            base = winreg.OpenKey(root, r"SOFTWARE\Clients\StartMenuInternet")
        except OSError:
            continue
        with base:
            try:
                default_name = default_name or winreg.QueryValue(base, None) or ""
            except OSError:
                pass
            index = 0
            while True:
                try:
                    key_name = winreg.EnumKey(base, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(base, key_name) as key:
                        display = winreg.QueryValue(key, None) or key_name
                        command = winreg.QueryValue(key, r"shell\open\command") or ""
                        command = command.strip().strip('"')
                        try:
                            icon = winreg.QueryValue(key, "DefaultIcon") or ""
                        except OSError:
                            icon = ""
                        icon = icon.split(",")[0].strip().strip('"')
                except OSError:
                    continue
                if not command or not Path(command).is_file():
                    continue
                if display not in found:
                    found[display] = Browser(display, command, icon or command,
                                             is_default=(key_name == default_name))
    return list(found.values())


def _linux_browsers() -> list[Browser]:
    found = []
    for name, executables in _LINUX_CANDIDATES:
        for executable in executables:
            path = shutil.which(executable)
            if path:
                found.append(Browser(name, path))
                break
    return found


def _macos_browsers() -> list[Browser]:
    return [Browser(name, path) for name, path in _MACOS_CANDIDATES if Path(path).exists()]


def find_browsers() -> list[Browser]:
    """Installed browsers, most familiar first, default browser promoted."""
    if os.name == "nt":
        browsers = _windows_browsers()
    elif sys.platform == "darwin":
        browsers = _macos_browsers()
    else:
        browsers = _linux_browsers()

    def sort_key(b: Browser) -> tuple[int, int, str]:
        known = _KNOWN_ORDER.index(b.name) if b.name in _KNOWN_ORDER else len(_KNOWN_ORDER)
        return (0 if b.is_default else 1, known, b.name.lower())

    return sorted(browsers, key=sort_key)
