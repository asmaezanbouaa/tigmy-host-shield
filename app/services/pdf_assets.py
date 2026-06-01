"""Official PDF assets — coat of arms for headers."""

from pathlib import Path

from PIL import Image

from app.config import PROJECT_ROOT

COAT_SOURCE = PROJECT_ROOT / "config" / "morocco_coat_of_arms.png"
COAT_HEADER = PROJECT_ROOT / "config" / "morocco_coat_header.png"
MAX_HEADER_COAT_HEIGHT = 200


def _remove_dark_background(img: Image.Image) -> Image.Image:
    """Drop black backdrop so the emblem shows on the green header band."""
    img = img.convert("RGBA")
    data = img.getdata()
    new = []
    for r, g, b, a in data:
        if r < 55 and g < 55 and b < 55:
            new.append((r, g, b, 0))
        else:
            new.append((r, g, b, a))
    img.putdata(new)
    return img


def ensure_coat_header_image() -> Path:
    """Coat of arms sized for the green PDF header band."""
    if not COAT_SOURCE.exists():
        return COAT_SOURCE

    if COAT_HEADER.exists() and COAT_HEADER.stat().st_mtime >= COAT_SOURCE.stat().st_mtime:
        return COAT_HEADER

    img = Image.open(COAT_SOURCE)
    img = _remove_dark_background(img)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    w, h = img.size
    if h > MAX_HEADER_COAT_HEIGHT:
        ratio = MAX_HEADER_COAT_HEIGHT / h
        img = img.resize((int(w * ratio), MAX_HEADER_COAT_HEIGHT), Image.Resampling.LANCZOS)

    COAT_HEADER.parent.mkdir(parents=True, exist_ok=True)
    img.save(COAT_HEADER, format="PNG", optimize=True)
    return COAT_HEADER


def ensure_fiche_banner() -> Path:
    return ensure_coat_header_image()


def ensure_rules_banner() -> Path:
    return ensure_coat_header_image()


def ensure_coat_for_pdf() -> Path:
    return ensure_coat_header_image()
