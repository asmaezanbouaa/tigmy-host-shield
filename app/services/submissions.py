"""Submission workflow: confirm, archive, edit, purge."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import Document, Submission, SubmissionStatus
from app.services.registry_meta import (
    KEY_ARCHIVE_LAST_PURGE_AT,
    KEY_ARCHIVE_PURGED_TOTAL,
    get_int,
    set_int,
    set_iso_datetime,
)
from app.services.storage import absolute_path, unlink_if_exists
from app.services.property_placeholder import get_or_create_placeholder_apartment
from app.services.submission_pdfs import regenerate_submission_pdfs


def confirm_submission(db: Session, submission: Submission) -> str:
    submission.status = SubmissionStatus.CONFIRMED.value
    submission.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    return "Submission confirmed."


def archive_submission(db: Session, submission: Submission) -> str:
    submission.status = SubmissionStatus.ARCHIVED.value
    submission.archived_at = datetime.now(timezone.utc)
    db.commit()
    return "Submission moved to archive."


def update_submission_from_admin(
    db: Session,
    submission: Submission,
    *,
    last_name: str,
    first_name: str,
    nationality: str,
    date_of_birth: str,
    country_of_residence: str,
    number_of_guests: int,
    number_of_kids: int,
    arrival_date: str,
    departure_date: str,
    id_document_type: str,
    id_document_number: str,
    admin_notes: str | None = None,
) -> None:
    submission.apartment_id = get_or_create_placeholder_apartment(db).id
    submission.last_name = last_name
    submission.first_name = first_name
    submission.nationality = nationality
    submission.date_of_birth = date_of_birth
    submission.country_of_residence = country_of_residence
    submission.number_of_guests = number_of_guests
    submission.number_of_kids = number_of_kids
    submission.arrival_date = arrival_date
    submission.departure_date = departure_date
    submission.id_document_type = id_document_type
    submission.id_document_number = id_document_number
    if admin_notes is not None:
        submission.admin_notes = admin_notes or None
    db.flush()

    full = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.id == submission.id)
        .first()
    )
    if full:
        regenerate_submission_pdfs(db, full)
    db.commit()


def permanently_delete_submission(db: Session, submission: Submission) -> None:
    if submission.document:
        unlink_if_exists(submission.document.pdf_path)
        unlink_if_exists(submission.document.rules_pdf_path)
        db.delete(submission.document)

    unlink_if_exists(submission.signature_path)
    unlink_if_exists(submission.id_document_path)

    db.delete(submission)
    db.commit()


def purge_all_archived(db: Session) -> tuple[int, int]:
    """Delete all archived rows and files; return (purged_count, new_cumulative_total)."""
    archived = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.status == SubmissionStatus.ARCHIVED.value)
        .all()
    )
    count = len(archived)
    for sub in archived:
        if sub.document:
            unlink_if_exists(sub.document.pdf_path)
            unlink_if_exists(sub.document.rules_pdf_path)
            db.delete(sub.document)
        unlink_if_exists(sub.signature_path)
        unlink_if_exists(sub.id_document_path)
        db.delete(sub)

    cumulative = get_int(db, KEY_ARCHIVE_PURGED_TOTAL, 0) + count
    set_int(db, KEY_ARCHIVE_PURGED_TOTAL, cumulative)
    set_iso_datetime(db, KEY_ARCHIVE_LAST_PURGE_AT, datetime.now(timezone.utc))
    db.commit()
    return count, cumulative
