import base64
import re
from pathlib import Path
from uuid import uuid4

from app.config import get_settings

settings = get_settings()

DATA_URL_PATTERN = re.compile(
    r"^data:image/(?P<fmt>png|jpeg|jpg);base64,(?P<data>[A-Za-z0-9+/=\s]+)$"
)

ALLOWED_ID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_ID_BYTES = 10 * 1024 * 1024


def ensure_storage_dirs() -> None:
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    settings.signatures_path.mkdir(parents=True, exist_ok=True)
    settings.pdfs_path.mkdir(parents=True, exist_ok=True)
    settings.id_documents_path.mkdir(parents=True, exist_ok=True)
    settings.archive_exports_path.mkdir(parents=True, exist_ok=True)
    (settings.storage_path.parent / "data").mkdir(parents=True, exist_ok=True)


def save_signature_from_data_url(data_url: str, submission_public_id: str) -> str:
    match = DATA_URL_PATTERN.match(data_url.strip())
    if not match:
        raise ValueError("Invalid signature image")

    fmt = match.group("fmt").lower()
    ext = "jpg" if fmt in ("jpeg", "jpg") else "png"

    raw = match.group("data").replace("\n", "").replace(" ", "")
    try:
        image_bytes = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("Invalid signature encoding") from exc

    if len(image_bytes) < 100 or len(image_bytes) > 2_000_000:
        raise ValueError("Signature file size out of range")

    filename = f"{submission_public_id}_{uuid4().hex[:8]}.{ext}"
    path = settings.signatures_path / filename
    path.write_bytes(image_bytes)
    return str(path.relative_to(settings.storage_path.parent))


def save_id_document(file_bytes: bytes, filename: str, submission_public_id: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_ID_EXTENSIONS:
        raise ValueError("ID file must be JPG, PNG, or PDF")
    if len(file_bytes) < 1024 or len(file_bytes) > MAX_ID_BYTES:
        raise ValueError("ID file size must be between 1 KB and 10 MB")

    safe_ext = ext if ext != ".jpeg" else ".jpg"
    out_name = f"{submission_public_id}_{uuid4().hex[:8]}{safe_ext}"
    path = settings.id_documents_path / out_name
    path.write_bytes(file_bytes)
    return str(path.relative_to(settings.storage_path.parent))


def absolute_path(relative: str) -> Path:
    return settings.storage_path.parent / relative


def unlink_if_exists(relative: str | None) -> None:
    if not relative:
        return
    path = absolute_path(relative)
    if path.exists():
        path.unlink()
