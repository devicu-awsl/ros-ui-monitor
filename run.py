"""Frozen-build entry point.

PyInstaller executes its entry script as ``__main__``, i.e. as a plain
top-level module with no parent package.  Pointing it straight at
``app/main.py`` therefore breaks every relative import in that file
("attempted relative import with no known parent package").

This launcher lives outside the package and imports it absolutely, so the
``app`` package is imported normally and all of its relative imports resolve.

    pyinstaller rb5009-monitor.spec      # bundles this file
    python run.py --version              # same behaviour from source
"""

from __future__ import annotations

from app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
