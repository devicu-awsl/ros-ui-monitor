"""QR encoding for the LAN URL (no Qt needed)."""

import struct

import pytest

from app.qr import qr_available, qr_png

pytestmark = pytest.mark.skipif(not qr_available(), reason="segno not installed")

LAN_URL = "http://192.168.88.50:8000/"


def _png_size(data: bytes) -> tuple[int, int]:
    """Width and height straight out of the PNG IHDR chunk."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_produces_a_square_png():
    width, height = _png_size(qr_png(LAN_URL, 220))
    assert width == height


def test_fits_within_the_requested_size():
    for requested in (140, 220, 300):
        width, _ = _png_size(qr_png(LAN_URL, requested))
        assert width <= requested, f"{width} exceeded requested {requested}"
        # Whole-module scaling means it will not hit the target exactly, but
        # it should not be wildly undersized either.
        assert width > requested * 0.7


def test_larger_request_gives_a_larger_code():
    small, _ = _png_size(qr_png(LAN_URL, 150))
    large, _ = _png_size(qr_png(LAN_URL, 300))
    assert large > small


def test_tiny_request_still_renders():
    width, _ = _png_size(qr_png(LAN_URL, 10))
    assert width > 0


def test_longer_urls_still_encode():
    long_url = "http://192.168.88.50:8000/some/deep/path?with=query&and=more"
    assert _png_size(qr_png(long_url, 220))[0] > 0


def test_round_trips_through_a_decoder():
    """The generated code must actually scan back to the URL."""
    cv2 = pytest.importorskip("cv2", reason="opencv not installed")
    numpy = pytest.importorskip("numpy")

    png = qr_png(LAN_URL, 260)
    image = cv2.imdecode(numpy.frombuffer(png, numpy.uint8), cv2.IMREAD_COLOR)
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
    assert decoded == LAN_URL
