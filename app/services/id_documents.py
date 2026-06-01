"""Guest ID scan upload, admin verification, 14-hour retention."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Submission
from app.services.storage import unlink_if_exists

settings = get_settings()


def verify_id_document(db: Session, submission: Submission) -> None:
    submission.id_document_verified_at = datetime.now(timezone.utc)
    db.commit()


def purge_expired_id_documents(db: Session) -> int:
    """Delete ID files verified more than retention_hours ago."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.id_retention_hours_after_verify)
    removed = 0

    rows = (
        db.query(Submission)
        .filter(
            Submission.id_document_path.isnot(None),
            Submission.id_document_verified_at.isnot(None),
            Submission.id_document_verified_at <= cutoff,
        )
        .all()
    )
    for sub in rows:
        unlink_if_exists(sub.id_document_path)
        sub.id_document_path = None
        sub.id_document_verified_at = None
        removed += 1

    if removed:
        db.commit()
    return removed
