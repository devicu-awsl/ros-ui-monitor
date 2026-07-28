# PyInstaller spec for the Phase A Windows single-file executable.
# Build on Windows:  pyinstaller rb5009-monitor.spec
# Output:            dist/rb5009-monitor.exe

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("app/templates", "app/templates"),
        ("app/static", "app/static"),
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
    excludes=["tkinter"],
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
