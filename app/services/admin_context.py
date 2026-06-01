"""Shared admin dashboard counts and submission queries."""

from datetime import date, datetime, time, timezone
from urllib.parse import urlencode

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models import ACTIVE_SUBMISSION_STATUSES, Submission, SubmissionStatus
from app.services.registry_meta import KEY_ARCHIVE_PURGED_TOTAL, get_int


def parse_filter_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        d = date.fromisoformat(value.strip()[:10])
        return datetime.combine(d, time.min, tzinfo=timezone.utc)
    except ValueError:
        return None


def get_overview_dashboard(db: Session) -> dict:
    """Today's arrivals, ID verifications pending, and submissions needing action."""
    today = date.today().isoformat()
    base_active = db.query(Submission).filter(
        Submission.status.in_(ACTIVE_SUBMISSION_STATUSES)
    )

    today_arrivals = (
        base_active.filter(Submission.arrival_date == today)
        .order_by(Submission.submitted_at.desc())
        .limit(8)
        .all()
    )

    pending_id = (
        db.query(func.count(Submission.id))
        .filter(
            Submission.status == SubmissionStatus.SUBMITTED.value,
            Submission.id_document_path.isnot(None),
            Submission.id_document_path != "",
            Submission.id_document_verified_at.is_(None),
        )
        .scalar()
        or 0
    )

    need_action_count = (
        db.query(func.count(Submission.id))
        .filter(
            Submission.status.in_(
                (SubmissionStatus.SUBMITTED.value, SubmissionStatus.ISSUE.value)
            )
        )
        .scalar()
        or 0
    )

    need_action = (
        db.query(Submission)
        .filter(
            Submission.status.in_(
                (SubmissionStatus.SUBMITTED.value, SubmissionStatus.ISSUE.value)
            )
        )
        .order_by(Submission.submitted_at.desc())
        .limit(10)
        .all()
    )

    departing_today = (
        base_active.filter(Submission.departure_date == today)
        .order_by(Submission.last_name)
        .limit(5)
        .all()
    )

    today_arrivals_count = (
        db.query(func.count(Submission.id))
        .filter(
            Submission.status.in_(ACTIVE_SUBMISSION_STATUSES),
            Submission.arrival_date == today,
        )
        .scalar()
        or 0
    )

    return {
        "today_iso": today,
        "today_arrivals_count": today_arrivals_count,
        "today_arrivals": today_arrivals,
        "departing_today": departing_today,
        "pending_id_count": pending_id,
        "need_action": need_action,
        "need_action_count": need_action_count,
    }


def get_admin_counts(db: Session) -> dict[str, int]:
    current_archived = (
        db.query(func.count(Submission.id))
        .filter(Submission.status == SubmissionStatus.ARCHIVED.value)
        .scalar()
        or 0
    )
    purged_total = get_int(db, KEY_ARCHIVE_PURGED_TOTAL, 0)
    return {
        "pending_count": (
            db.query(func.count(Submission.id))
            .filter(Submission.status == SubmissionStatus.SUBMITTED.value)
            .scalar()
            or 0
        ),
        "confirmed_count": (
            db.query(func.count(Submission.id))
            .filter(Submission.status == SubmissionStatus.CONFIRMED.value)
            .scalar()
            or 0
        ),
        "total_active": (
            db.query(func.count(Submission.id))
            .filter(Submission.status.in_(ACTIVE_SUBMISSION_STATUSES))
            .scalar()
            or 0
        ),
        "archive_current": current_archived,
        "archive_purged_total": purged_total,
        "archive_count": current_archived + purged_total,
    }


def query_submissions(
    db: Session,
    *,
    q: str | None = None,
    status_filter: str | None = None,
    arrival_from: str | None = None,
    arrival_to: str | None = None,
    submitted_from: str | None = None,
    submitted_to: str | None = None,
) -> list[Submission]:
    query = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.status.in_(ACTIVE_SUBMISSION_STATUSES))
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
