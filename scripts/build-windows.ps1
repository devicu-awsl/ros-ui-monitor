# Build the Phase A Windows executable locally.
# Requires Python 3.11+ on Windows (PyInstaller is not a cross-compiler).
#
#   powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pip install --upgrade pip
python -m pip install ".[dev]"

pyinstaller rb5009-monitor.spec --clean --noconfirm

Write-Host ""
Write-Host "Build complete: dist\rb5009-monitor.exe"
