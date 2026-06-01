"""Render ID scans as images for inline admin preview."""

from pathlib import Path


def get_preview_image(path: Path) -> tuple[bytes, str]:
    """Return image bytes and media type for browser display."""
    suffix = path.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        return path.read_bytes(), "image/jpeg"
    if suffix == ".png":
        return path.read_bytes(), "image/png"
    if suffix == ".pdf":
        try:
            import fitz

            doc = fitz.open(str(path))
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            return pix.tobytes("png"), "image/png"
        except ImportError:
            raise ValueError("PDF preview requires pymupdf") from None
    raise ValueError(f"Unsupported ID file type: {suffix}")
