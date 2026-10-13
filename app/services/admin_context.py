"""Shared admin dashboard counts and submission queries."""

from datetime import date, datetime, time, timezone
from urllib.parse import urlencode

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import ACTIVE_SUBMISSION_STATUSES, Submission, SubmissionStatus
from app.services.registry_meta import KEY_ARCHIVE_PURGED_TOTAL, get_int, section_key


def parse_filter_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        d = date.fromisoformat(value.strip()[:10])
        return datetime.combine(d, time.min, tzinfo=timezone.utc)
    except ValueError:
        return None


def get_admin_counts(db: Session, section_id: int) -> dict[str, int]:
    def count(*conds) -> int:
        return (
            db.query(func.count(Submission.id))
            .filter(Submission.section_id == section_id, *conds)
            .scalar()
            or 0
        )

    current_archived = count(Submission.status == SubmissionStatus.ARCHIVED.value)
    purged_total = get_int(db, section_key(KEY_ARCHIVE_PURGED_TOTAL, section_id), 0)
    return {
        "pending_count": count(Submission.status == SubmissionStatus.SUBMITTED.value),
        "confirmed_count": count(Submission.status == SubmissionStatus.CONFIRMED.value),
        "ai_auto_confirmed_count": count(Submission.ai_auto_confirmed.is_(True)),
        # AI approved the ID but the host has not picked an apartment / confirmed yet
        "ai_awaiting_apartment_count": count(
            Submission.ai_auto_confirmed.is_(True),
            Submission.status == SubmissionStatus.SUBMITTED.value,
        ),
        "ai_needs_review_count": count(
            Submission.status == SubmissionStatus.SUBMITTED.value,
            Submission.ai_verification_at.isnot(None),
            Submission.ai_auto_confirmed.is_(False),
        ),
        "total_active": count(Submission.status.in_(ACTIVE_SUBMISSION_STATUSES)),
        "archive_current": current_archived,
        "archive_purged_total": purged_total,
        "archive_count": current_archived + purged_total,
    }


def query_submissions(
    db: Session,
    section_id: int,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    ai_filter: str | None = None,
    arrival_from: str | None = None,
    arrival_to: str | None = None,
    submitted_from: str | None = None,
    submitted_to: str | None = None,
) -> list[Submission]:
    query = (
        db.query(Submission)
        .options(joinedload(Submission.document), joinedload(Submission.apartment))
        .filter(
            Submission.section_id == section_id,
            Submission.status.in_(ACTIVE_SUBMISSION_STATUSES),
        )
        .order_by(Submission.submitted_at.desc())
    )
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Submission.last_name.ilike(term),
                Submission.first_name.ilike(term),
                Submission.id_document_number.ilike(term),
            )
        )
    allowed = {s.value for s in SubmissionStatus}
    if status_filter and status_filter.strip() in allowed:
        query = query.filter(Submission.status == status_filter.strip())

    ai = (ai_filter or "").strip().lower()
    if ai == "auto_confirmed":
        query = query.filter(Submission.ai_auto_confirmed.is_(True))
    elif ai == "needs_review":
        query = query.filter(
            Submission.status == SubmissionStatus.SUBMITTED.value,
            Submission.ai_verification_at.isnot(None),
            Submission.ai_auto_confirmed.is_(False),
        )

    if arrival_from and arrival_from.strip():
        query = query.filter(Submission.arrival_date >= arrival_from.strip()[:10])
    if arrival_to and arrival_to.strip():
        query = query.filter(Submission.arrival_date <= arrival_to.strip()[:10])
    submitted_from_dt = parse_filter_date(submitted_from)
    if submitted_from_dt is not None:
        query = query.filter(Submission.submitted_at >= submitted_from_dt)
    submitted_to_dt = parse_filter_date(submitted_to)
    if submitted_to_dt is not None:
        end = datetime.combine(submitted_to_dt.date(), time.max, tzinfo=timezone.utc)
        query = query.filter(Submission.submitted_at <= end)
    return query.limit(200).all()


def query_ai_auto_confirmed(db: Session, section_id: int, *, limit: int = 100) -> list[Submission]:
    return (
        db.query(Submission)
        .options(joinedload(Submission.document), joinedload(Submission.apartment))
        .filter(
            Submission.section_id == section_id,
            Submission.ai_auto_confirmed.is_(True),
            Submission.status != SubmissionStatus.ARCHIVED.value,
        )
        .order_by(Submission.submitted_at.desc())
        .limit(limit)
        .all()
    )


def build_export_url(
    *,
    status_filter: str | None = None,
    arrival_from: str | None = None,
    arrival_to: str | None = None,
    submitted_from: str | None = None,
    submitted_to: str | None = None,
    include_archived: bool = False,
) -> str:
    params: dict[str, str] = {}
    if status_filter and status_filter.strip():
        params["status_filter"] = status_filter.strip()
    if arrival_from and arrival_from.strip():
        params["arrival_from"] = arrival_from.strip()[:10]
    if arrival_to and arrival_to.strip():
        params["arrival_to"] = arrival_to.strip()[:10]
    if submitted_from and submitted_from.strip():
        params["submitted_from"] = submitted_from.strip()[:10]
    if submitted_to and submitted_to.strip():
        params["submitted_to"] = submitted_to.strip()[:10]
    if include_archived:
        params["include_archived"] = "true"
    url = "/admin/export.csv"
    if params:
        url += "?" + urlencode(params)
    return url


def filters_active(**kwargs) -> bool:
    for key, val in kwargs.items():
        if key == "include_archived":
            continue
        if val and str(val).strip():
            return True
    return False
