# PyInstaller spec for the Windows single-file executable.
# The same executable serves Phase A (localhost) and Phase B (--lan).
# Build on Windows:  pyinstaller rb5009-monitor.spec
# Output:            dist/rb5009-monitor.exe
#
# The entry point is run.py, not app/main.py: PyInstaller executes the entry
# script as __main__ with no parent package, so a module from inside the "app"
# package cannot be used directly - its relative imports fail at startup with
# "attempted relative import with no known parent package".
#
# Paths are anchored to SPECPATH so the build works from any directory.
# Phase A/B serve a plain static dashboard, so app/static is the only data
# directory to bundle; there is no template directory.

#
# The --chooser launcher window needs PySide6, which adds tens of megabytes.
# PyInstaller follows imports inside function bodies, so it would bundle Qt
# into every build unless it is excluded explicitly. Set RBMON_BUILD_GUI=1 to
# produce the larger executable that includes the launcher.

import os

ROOT = os.path.abspath(SPECPATH)  # noqa: F821 - injected by PyInstaller

WITH_GUI = os.environ.get("RBMON_BUILD_GUI", "").strip().lower() in ("1", "true", "yes")
EXCLUDES = ["tkinter"] if WITH_GUI else ["tkinter", "PySide6", "shiboken6", "segno"]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "app", "static"), "app/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rb5009-monitor",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
