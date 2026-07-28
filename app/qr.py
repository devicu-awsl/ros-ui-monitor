"""QR rendering for the LAN URL, so a phone or tablet can open the dashboard
without anyone typing an IP address.

No Qt import here, so the encoding can be tested on its own.
"""

from __future__ import annotations

import io

# Quiet zone in modules. The QR spec asks for 4; 3 still scans reliably on
# screen and keeps the code larger within the same box.
QUIET_ZONE = 3


def qr_png(data: str, size_px: int = 220,
           dark: str = "#0b0e12", light: str = "#ffffff") -> bytes:
    """PNG bytes for a QR code of `data`, sized to fit `size_px` square.

    Rendered dark-on-light regardless of the surrounding theme: inverted QR
    codes are unreliable to scan on many phone cameras.
    """
    import segno  # imported lazily so the module stays cheap to import

    qr = segno.make(data, error="m")
    modules = qr.symbol_size(scale=1, border=QUIET_ZONE)[0]
    # segno only scales by whole modules, so round down to stay within size_px.
    scale = max(1, size_px // modules)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=scale, border=QUIET_ZONE, dark=dark, light=light)
    return buffer.getvalue()


def qr_available() -> bool:
    try:
        import segno  # noqa: F401
    except ImportError:
        return False
    return True
