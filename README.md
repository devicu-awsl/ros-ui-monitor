# ros-ui-monitor

## Phase A

UI for MikroTik RouterOS diagnostic and monitoring tools. (Only test on RB5009)

Phase A delivers `rb5009-monitor.exe`: a Windows-first, LAN-only monitoring
dashboard for a MikroTik RB5009, built as a normal modular Python project
(FastAPI + Uvicorn + HTTPX + SQLite) and packaged with PyInstaller.

### Assumptions (Phase A)

- Router address: `192.168.88.1`
- RouterOS API service ports: TCP `8728` (api) and `8729` (api-ssl, secure)
- The REST API itself is served over HTTPS by the RouterOS `www-ssl` service;
  the REST base URL defaults to `https://192.168.88.1` and is configurable
  via `RBMON_ROUTER_URL`

### Features

- Live dashboard: CPU, memory, uptime, health sensors (discovered dynamically)
- Interface table with state, throughput (derived from counter deltas),
  errors, drops and link-down counts
- Throughput chart per interface (self-contained canvas renderer, no CDN —
  works with zero internet access)
- Server-Sent Events push updates; browsers never talk to the router directly
  and RouterOS credentials never leave the application host
- SQLite history (WAL mode) with retention pruning, plus event log
  (connectivity changes, interface up/down, counter resets)
- Stale-data age indicators instead of silently showing old data as live
- `/healthz` and `/readyz` endpoints; clean shutdown so SQLite is never corrupted

### Quick start (from source)

```bash
pip install .
rb5009-monitor --no-browser        # or: python -m app.main
```

Windows executable usage:

```text
rb5009-monitor.exe
rb5009-monitor.exe --host 0.0.0.0 --port 8000
rb5009-monitor.exe --no-browser
rb5009-monitor.exe --config "C:\ProgramData\RB5009Monitor\config.env"
```

### Configuration

Copy `config/config.example.env`, fill in the dedicated read-only RouterOS
monitoring user, and pass it with `--config` (or set `RBMON_*` environment
variables — the environment overrides the file). Data is stored outside the
executable, by default in `C:\ProgramData\RB5009Monitor\` on Windows.

Create the monitoring user on the router with a custom group (avoid the
built-in `read` group) limited to `rest-api` + `read`, restricted to the
monitoring PC's source address, and enable `www-ssl`.

### Building the Windows executable

Locally (on Windows — PyInstaller is not a cross-compiler):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1
# -> dist\rb5009-monitor.exe
```

### Releases (automatic)

Every push to `main` triggers `.github/workflows/release.yml`, which builds
the executable on a Windows runner and publishes a GitHub Release:

- Tag and release title: `vX.Y`
  - `X` = phase number from the `PHASE` file (Phase A → `1`)
  - `Y` = auto-incremented per release, starting at `v1.1`
- Attached binary: `ros-ui-monitor_vX_Y.exe`

When Phase B starts, change the `PHASE` file content from `1` to `2` and the
next release will be `v2.1`.

### Tests

```bash
pip install ".[dev]"
pytest
```

### Roadmap

- **Phase A — Windows:** run `rb5009-monitor.exe` on an existing Windows PC (this release)
- **Phase B — Windows LAN mode:** trusted tablets/phones access the responsive web UI
- **Phase C — NAS/Debian or Docker:** move source, config and SQLite DB to an always-on server
- **Phase D — PWA:** trusted HTTPS, manifest, service worker, home-screen install
