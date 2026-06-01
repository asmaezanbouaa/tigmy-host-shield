"""Quarterly ZIP export of archived submissions."""

import io
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.models import Submission, SubmissionStatus
from app.services.export_data import build_submissions_csv
from app.services.registry_meta import KEY_ARCHIVE_LAST_PURGE_AT, get_iso_datetime
from app.services.storage import absolute_path

settings = get_settings()


def archived_submissions(db: Session) -> list[Submission]:
    return (
        db.query(Submission)
        .options(joinedload(Submission.apartment), joinedload(Submission.document))
        .filter(Submission.status == SubmissionStatus.ARCHIVED.value)
        .order_by(Submission.archived_at.desc())
        .all()
    )


def build_archive_zip(db: Session) -> bytes | None:
    subs = archived_submissions(db)
    if not subs:
        return None

    buf = io.BytesIO()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        csv_data = build_submissions_csv(db, include_archived=True, status_filter="archived")
        zf.writestr(f"archived_registrations_{stamp}.csv", csv_data)

        for sub in subs:
            folder = f"{sub.last_name}_{sub.first_name}_{sub.public_id[:8]}"
            if sub.document:
                fiche = absolute_path(sub.document.pdf_path)
                if fiche.exists():
                    zf.write(fiche, f"{folder}/{sub.document.filename}")
                if sub.document.rules_pdf_path:
                    rules = absolute_path(sub.document.rules_pdf_path)
                    if rules.exists() and sub.document.rules_filename:
                        zf.write(rules, f"{folder}/{sub.document.rules_filename}")
            if sub.signature_path:
                sig = absolute_path(sub.signature_path)
                if sig.exists():
                    zf.write(sig, f"{folder}/signature{sig.suffix}")

    buf.seek(0)
    return buf.getvalue()


def can_quarterly_purge(db: Session) -> tuple[bool, str]:
    """True if 90 days passed since last purge (or never purged)."""
    last = get_iso_datetime(db, KEY_ARCHIVE_LAST_PURGE_AT)
    if last is None:
        return True, "No previous quarterly purge on record."
    days = settings.archive_purge_interval_days
    next_due = last + timedelta(days=days)
    now = datetime.now(timezone.utc)
    if now >= next_due:
        return True, f"Last purge: {last.strftime('%Y-%m-%d')}. Ready for new cycle."
    remaining = (next_due - now).days
    return False, f"Next purge available in {remaining} day(s) (last: {last.strftime('%Y-%m-%d')})."
