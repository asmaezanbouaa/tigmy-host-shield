"""Platform-wide statistics for the owner: every section, admin and guest."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import AdminUser, Apartment, HostSection, Submission, SubmissionStatus
from app.services.packs import host_state, pending_orders_count

STATUS_ORDER = [
    (SubmissionStatus.SUBMITTED.value, "À traiter"),
    (SubmissionStatus.CONFIRMED.value, "Confirmées"),
    (SubmissionStatus.ISSUE.value, "Problèmes"),
    (SubmissionStatus.ARCHIVED.value, "Archivées"),
]


def _nights(sub: Submission) -> int:
    try:
        a = date.fromisoformat(sub.arrival_date[:10])
        d = date.fromisoformat(sub.departure_date[:10])
    except ValueError:
        return 0
    return max((d - a).days, 0)


def _pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def _summarize(subs: list[Submission]) -> dict:
    by_status = Counter(s.status for s in subs)
    ai_checked = [s for s in subs if s.ai_verification_at is not None]
    ai_approved = [s for s in ai_checked if s.ai_auto_confirmed]
    confirmed = [s for s in subs if s.status == SubmissionStatus.CONFIRMED.value]
    decided = by_status[SubmissionStatus.CONFIRMED.value] + by_status[SubmissionStatus.ISSUE.value]
    return {
        "guests": len(subs),
        "people": sum(s.number_of_guests for s in subs),
        "pending": by_status[SubmissionStatus.SUBMITTED.value],
        "awaiting_apartment": sum(
            1 for s in subs if s.ai_auto_confirmed and s.status == SubmissionStatus.SUBMITTED.value
        ),
        "confirmed": len(confirmed),
        "issue": by_status[SubmissionStatus.ISSUE.value],
        "archived": by_status[SubmissionStatus.ARCHIVED.value],
        "ai_checked": len(ai_checked),
        "ai_approval_rate": _pct(len(ai_approved), len(ai_checked)),
        "confirmation_rate": _pct(by_status[SubmissionStatus.CONFIRMED.value], decided),
        "nights": sum(_nights(s) for s in confirmed),
        "last_registration": max((s.submitted_at for s in subs), default=None),
        "by_status": by_status,
    }


def build_platform_stats(db: Session, days: int = 30) -> dict:
    sections = db.query(HostSection).order_by(HostSection.created_at, HostSection.id).all()
    subs = db.query(Submission).options(joinedload(Submission.apartment)).all()
    admins = db.query(AdminUser).order_by(AdminUser.username).all()
    apartments = db.query(Apartment).filter(Apartment.section_id.isnot(None)).all()

    subs_by_section: dict[int | None, list[Submission]] = defaultdict(list)
    for s in subs:
        subs_by_section[s.section_id].append(s)
    admins_by_section: dict[int | None, list[AdminUser]] = defaultdict(list)
    for a in admins:
        admins_by_section[a.section_id].append(a)
    apts_by_section = Counter(a.section_id for a in apartments if a.is_active)

    rows = []
    for sec in sections:
        rows.append(
            {
                "section": sec,
                "admins": admins_by_section.get(sec.id, []),
                "apartments": apts_by_section.get(sec.id, 0),
                "pack": host_state(db, sec.id),
                "pending_orders": pending_orders_count(db, sec.id),
                **_summarize(subs_by_section.get(sec.id, [])),
            }
        )

    total = _summarize(subs)

    # Registrations per day (all sections), oldest first
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    per_day = Counter()
    for s in subs:
        when = s.submitted_at
        if when is None:
            continue
        d = when.date()
        if d >= start:
            per_day[d] += 1
    daily = [{"date": start + timedelta(days=i), "count": per_day[start + timedelta(days=i)]} for i in range(days)]

    nationalities = Counter((s.nationality or "").strip().title() for s in subs if (s.nationality or "").strip())
    top_nat = nationalities.most_common(6)
    other_nat = sum(nationalities.values()) - sum(c for _, c in top_nat)

    statuses = [
        {"key": key, "label": label, "count": total["by_status"][key]} for key, label in STATUS_ORDER
    ]

    return {
        "total": total,
        "sections_total": len(sections),
        "sections_active": sum(1 for s in sections if s.is_active),
        "admins_total": sum(1 for a in admins if a.section_id is not None),
        "admins_blocked": sum(1 for a in admins if a.section_id is not None and not a.is_active),
        "apartments_total": sum(apts_by_section.values()),
        "rows": rows,
        "pending_orders_total": pending_orders_count(db),
        "packs_exhausted": sum(1 for r in rows if r["pack"].status in ("exhausted", "expired")),
        "daily": daily,
        "daily_max": max((d["count"] for d in daily), default=0),
        "daily_total": sum(d["count"] for d in daily),
        "days": days,
        "nationalities": top_nat,
        "nationalities_other": other_nat,
        "nationalities_max": top_nat[0][1] if top_nat else 0,
        "statuses": statuses,
        "statuses_max": max((s["count"] for s in statuses), default=0),
    }
