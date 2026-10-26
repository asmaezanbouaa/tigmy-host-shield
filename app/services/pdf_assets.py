"""PDF assets: the TIGMI company logo (letterhead, footer and light watermark)."""

from pathlib import Path

from PIL import Image

from app.config import PROJECT_ROOT

LOGO_SOURCE = PROJECT_ROOT / "config" / "company_logo.png"   # TIGMI company logo (transparent PNG)
LOGO_PDF = PROJECT_ROOT / "config" / "logo_pdf.png"
LOGO_WATERMARK = PROJECT_ROOT / "config" / "logo_watermark.png"
WATERMARK_OPACITY = 0.035


def ensure_logo_assets() -> tuple[Path, Path]:
    """Company logo for the PDF header/footer, and a very light copy used as a page watermark."""
    if not LOGO_SOURCE.exists():
        return LOGO_PDF, LOGO_WATERMARK
    fresh = LOGO_SOURCE.stat().st_mtime
    if not (LOGO_PDF.exists() and LOGO_PDF.stat().st_mtime >= fresh):
        Image.open(LOGO_SOURCE).convert("RGBA").save(LOGO_PDF, optimize=True)
    if not (LOGO_WATERMARK.exists() and LOGO_WATERMARK.stat().st_mtime >= fresh):
        logo = Image.open(LOGO_SOURCE).convert("RGBA")
        alpha = logo.getchannel("A").point(lambda a: int(a * WATERMARK_OPACITY))
        logo.putalpha(alpha)
        logo.save(LOGO_WATERMARK, optimize=True)
    return LOGO_PDF, LOGO_WATERMARK
