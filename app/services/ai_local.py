"""Free local ID check: OCR text from scan vs form fields (no API quota)."""

import difflib
import io
import re
from pathlib import Path

from PIL import Image

from app.models import Submission


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _ocr_text(image_bytes: bytes) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise ValueError(
            "Local OCR needs pytesseract. Run: pip install pytesseract "
            "and sudo apt install tesseract-ocr tesseract-ocr-fra"
        ) from exc

    img = Image.open(io.BytesIO(image_bytes))
    try:
        return pytesseract.image_to_string(img, lang="eng+fra+ara")
    except Exception:
        return pytesseract.image_to_string(img, lang="eng")


def _find_in_ocr(form_value: str, ocr: str) -> tuple[str, str, str]:
    """Return status, form_value, best id_value guess from OCR."""
    form = (form_value or "").strip()
    if not form:
        return "unclear", form, ""

    fn = _norm(form)
    ocr_raw = ocr or ""
    ocr_norm = _norm(ocr_raw)

    if not fn:
        return "unclear", form, ""

    if fn in ocr_norm:
        return "match", form, form

    # Date: allow YYYY-MM-DD vs DD/MM/YYYY
    if re.match(r"\d{4}-\d{2}-\d{2}", form):
        parts = form.split("-")
        variants = [
            form,
            f"{parts[2]}/{parts[1]}/{parts[0]}",
            f"{parts[2]}.{parts[1]}.{parts[0]}",
            "".join(parts),
        ]
        for v in variants:
            if _norm(v) in ocr_norm or v in ocr_raw:
                return "match", form, v

    ratio = difflib.SequenceMatcher(None, fn, ocr_norm).ratio()
    if ratio >= 0.82:
        return "match", form, "(similar in OCR)"
    if ratio >= 0.55:
        return "partial", form, "(partial OCR match)"

    # ID number: look for digit runs
    if re.search(r"\d", form):
        digits = re.sub(r"\D", "", form)
        if digits and digits in re.sub(r"\D", "", ocr_raw):
            return "match", form, digits

    return "mismatch", form, "(not found in OCR)"


def verify_local_ocr(sub: Submission, image_bytes: bytes) -> dict:
    ocr = _ocr_text(image_bytes)
    fields_spec = [
        ("last_name", sub.last_name),
        ("first_name", sub.first_name),
        ("date_of_birth", sub.date_of_birth),
        ("nationality", sub.nationality),
        ("id_document_number", sub.id_document_number),
    ]
    fields = []
    statuses = []
    for key, val in fields_spec:
        status, fv, idv = _find_in_ocr(val, ocr)
        fields.append(
            {
                "field": key,
                "form_value": fv,
                "id_value": idv,
                "status": status,
            }
        )
        statuses.append(status)

    if all(s == "match" for s in statuses):
        overall = "match"
    elif any(s == "mismatch" for s in statuses):
        overall = "partial" if any(s == "match" for s in statuses) else "mismatch"
    else:
        overall = "partial"

    match_count = sum(1 for s in statuses if s == "match")
    confidence = round(match_count / max(len(statuses), 1), 2)

    return {
        "overall": overall,
        "confidence": confidence,
        "summary": (
            f"Local OCR compared {match_count}/{len(statuses)} fields to the ID scan "
            "(no cloud AI — verify blurry or Arabic text yourself)."
        ),
        "fields": fields,
        "ocr_preview": ocr[:500] + ("…" if len(ocr) > 500 else ""),
    }
