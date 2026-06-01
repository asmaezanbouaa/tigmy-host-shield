"""Generate QR code PNG for guest registration URL."""

import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.services.public_urls import guest_register_url


def make_qr_png(url: str | None = None, size: int = 8) -> bytes:
    """Return PNG bytes for the given URL (default: /register)."""
    target = url or guest_register_url()
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=size,
        border=2,
    )
    qr.add_data(target)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1e3a5f", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
