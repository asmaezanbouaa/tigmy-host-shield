"""Build calendar month grid and stay list for admin."""

import calendar as cal_mod
from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import ACTIVE_SUBMISSION_STATUSES, Submission, SubmissionStatus


@dataclass
class CalendarEvent:
    public_id: str
    guest_name: str
    status: str
    arrival_date: str
    departure_date: str
    guests: int
    id_number: str
    detail_url: str

    @property
    def nights(self) -> int:
        try:
            a = date.fromisoformat(self.arrival_date[:10])
            d = date.fromisoformat(self.departure_date[:10])
            return max((d - a).days, 0)
        except ValueError:
            return 0


@dataclass
class CalendarDay:
    day: int | None  # None = padding cell
    iso: str | None
    is_today: bool
    events: list[CalendarEvent]


def _parse_date(s: str) -> date | None:
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def _event_on_day(ev: CalendarEvent, day_iso: str) -> bool:
    """True if stay overlaps this calendar day (inclusive)."""
    d = _parse_date(day_iso)
    arr = _parse_date(ev.arrival_date)
    dep = _parse_date(ev.departure_date)
    if not d or not arr or not dep:
        return False
    return arr <= d <= dep


def fetch_events_for_range(
    db: Session,
    range_start: date,
    range_end: date,
    include_archived: bool = False,
) -> list[CalendarEvent]:
    statuses = list(ACTIVE_SUBMISSION_STATUSES)
    if include_archived:
        statuses.append(SubmissionStatus.ARCHIVED.value)

    start_s = range_start.isoformat()
    end_s = range_end.isoformat()

    query = (
        db.query(Submission)
        .filter(Submission.status.in_(statuses))
        .filter(Submission.arrival_date <= end_s)
        .filter(Submission.departure_date >= start_s)
        .order_by(Submission.arrival_date, Submission.last_name)
    )

    events = []
    for sub in query.all():
        events.append(
            CalendarEvent(
                public_id=sub.public_id,
                guest_name=f"{sub.last_name} {sub.first_name}",
                status=sub.status,
                arrival_date=sub.arrival_date[:10],
                departure_date=sub.departure_date[:10],
                guests=sub.number_of_guests,
                id_number=sub.id_document_number or "",
                detail_url=f"/admin/submissions/{sub.public_id}",
            )
        )
    return events


def build_month_calendar(
    year: int,
    month: int,
    events: list[CalendarEvent],
    *,
    week_start: int = cal_mod.MONDAY,
) -> tuple[list[list[CalendarDay]], date, date]:
    """
    Returns (weeks grid, month_start, month_end).
    week_start: calendar.MONDAY (default) or SUNDAY.
    """
    today = datetime.now(timezone.utc).date()
    month_start = date(year, month, 1)
    last_day = cal_mod.monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    cal = cal_mod.Calendar(firstweekday=week_start)
    weeks: list[list[CalendarDay]] = []

    for week in cal.monthdatescalendar(year, month):
        row: list[CalendarDay] = []
        for cell_date in week:
            if cell_date.month != month:
                row.append(CalendarDay(day=None, iso=None, is_today=False, events=[]))
                continue
            iso = cell_date.isoformat()
            day_events = [e for e in events if _event_on_day(e, iso)]
            row.append(
                CalendarDay(
                    day=cell_date.day,
                    iso=iso,
                    is_today=cell_date == today,
                    events=day_events,
                )
            )
        weeks.append(row)

    return weeks, month_start, month_end


def month_nav(year: int, month: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Previous and next (year, month)."""
    if month == 1:
        prev_y, prev_m = year - 1, 12
    else:
        prev_y, prev_m = year, month - 1
    if month == 12:
        next_y, next_m = year + 1, 1
    else:
        next_y, next_m = year, month + 1
    return (prev_y, prev_m), (next_y, next_m)
