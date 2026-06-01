"""CSV export for guest submissions."""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import ACTIVE_SUBMISSION_STATUSES, Submission, SubmissionStatus
from app.services.property_placeholder import PROPERTY_PLACEHOLDER


CSV_COLUMNS = [
    "reference",
    "status",
    "last_name",
    "first_name",
    "establishment",
    "nationality",
    "date_of_birth",
    "country_of_residence",
    "guests",
    "children",
    "arrival_date",
    "departure_date",
    "id_document_type",
    "id_document_number",
    "submitted_at",
    "confirmed_at",
    "archived_at",
]


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def submission_to_row(sub: Submission) -> list[str]:
    return [
        sub.public_id,
        sub.status,
        sub.last_name,
        sub.first_name,
        PROPERTY_PLACEHOLDER,
        sub.nationality,
        sub.date_of_birth,
        sub.country_of_residence,
        str(sub.number_of_guests),
        str(sub.number_of_kids),
        sub.arrival_date,
        sub.departure_date,
        sub.id_document_type,
        sub.id_document_number,
        _fmt_dt(sub.submitted_at),
        _fmt_dt(sub.confirmed_at),
        _fmt_dt(sub.archived_at),
    ]


def build_submissions_csv(
    db: Session,
    *,
    include_archived: bool = False,
    status_filter: str | None = None,
    arrival_from: str | None = None,
    arrival_to: str | None = None,
) -> bytes:
    statuses = list(ACTIVE_SUBMISSION_STATUSES)
    if include_archived:
        statuses.append(SubmissionStatus.ARCHIVED.value)

    query = (
        db.query(Submission)
        .filter(Submission.status.in_(statuses))
        .order_by(Submission.arrival_date.desc(), Submission.submitted_at.desc())
    )

    if status_filter and status_filter.strip():
        query = query.filter(Submission.status == status_filter.strip())
    if arrival_from and arrival_from.strip():
        query = query.filter(Submission.arrival_date >= arrival_from.strip()[:10])
    if arrival_to and arrival_to.strip():
        query = query.filter(Submission.arrival_date <= arrival_to.strip()[:10])

    submissions = query.limit(5000).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for sub in submissions:
        writer.writerow(submission_to_row(sub))

    return buf.getvalue().encode("utf-8-sig")
