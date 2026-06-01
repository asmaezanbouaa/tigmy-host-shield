"""Shared date rules for guest registration."""

from datetime import date, timedelta

# Guest must be between 16 and 120 years old
MIN_AGE_YEARS = 16
MAX_AGE_YEARS = 120

# Arrival: up to 30 days in the past (late registration), max 2 years ahead
ARRIVAL_PAST_DAYS = 30
ARRIVAL_FUTURE_DAYS = 730

# Stay length: at least 1 night, max 365 days
MIN_STAY_DAYS = 1
MAX_STAY_DAYS = 365


def _safe_date(y: int, m: int, d: int) -> date:
    try:
        return date(y, m, d)
    except ValueError:
        return date(y, m, min(d, 28))


def parse_iso_date(value: str) -> date:
    raw = value.strip()[:10]
    if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
        raise ValueError("Invalid date format (use YYYY-MM-DD)")
    try:
        year = int(raw[0:4])
        month = int(raw[5:7])
        day = int(raw[8:10])
    except ValueError as exc:
        raise ValueError("Invalid date format (use YYYY-MM-DD)") from exc

    ref = today()
    if year < 1920 or year > ref.year + 3:
        raise ValueError("Year is not valid")
    if month < 1 or month > 12 or day < 1 or day > 31:
        raise ValueError("Invalid date")

    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise ValueError("Invalid date") from exc

    if parsed.year != year or parsed.month != month or parsed.day != day:
        raise ValueError("Invalid date")
    return parsed


def today() -> date:
    return date.today()


def validate_date_of_birth(dob: date, ref: date | None = None) -> None:
    ref = ref or today()
    if dob > ref:
        raise ValueError("Date of birth cannot be in the future")

    oldest = _safe_date(ref.year - MAX_AGE_YEARS, ref.month, ref.day)
    if dob < oldest:
        raise ValueError(f"Date of birth must be within the last {MAX_AGE_YEARS} years")

    youngest = _safe_date(ref.year - MIN_AGE_YEARS, ref.month, ref.day)
    if dob > youngest:
        raise ValueError(f"Guest must be at least {MIN_AGE_YEARS} years old")


def validate_arrival(arrival: date, ref: date | None = None) -> None:
    ref = ref or today()
    earliest = ref - timedelta(days=ARRIVAL_PAST_DAYS)
    latest = ref + timedelta(days=ARRIVAL_FUTURE_DAYS)

    if arrival < earliest:
        raise ValueError(
            f"Arrival date cannot be more than {ARRIVAL_PAST_DAYS} days in the past"
        )
    if arrival > latest:
        raise ValueError(
            f"Arrival date cannot be more than {ARRIVAL_FUTURE_DAYS // 365} years in the future"
        )


def validate_departure(arrival: date, departure: date, ref: date | None = None) -> None:
    ref = ref or today()
    if departure < arrival:
        raise ValueError("Departure date must be on or after arrival date")

    min_departure = arrival + timedelta(days=MIN_STAY_DAYS)
    if departure < min_departure:
        raise ValueError(f"Stay must be at least {MIN_STAY_DAYS} day(s)")

    max_departure = arrival + timedelta(days=MAX_STAY_DAYS)
    if departure > max_departure:
        raise ValueError(f"Stay cannot exceed {MAX_STAY_DAYS} days")

    global_latest = ref + timedelta(days=ARRIVAL_FUTURE_DAYS)
    if departure > global_latest:
        raise ValueError("Departure date is too far in the future")


def validate_stay_dates(arrival: date, departure: date, ref: date | None = None) -> None:
    validate_arrival(arrival, ref)
    validate_departure(arrival, departure, ref)


def date_limits_for_form(ref: date | None = None) -> dict:
    """ISO date strings for HTML min/max attributes."""
    ref = ref or today()
    return {
        "dob_min": _safe_date(ref.year - MAX_AGE_YEARS, ref.month, ref.day).isoformat(),
        "dob_max": _safe_date(ref.year - MIN_AGE_YEARS, ref.month, ref.day).isoformat(),
        "arrival_min": (ref - timedelta(days=ARRIVAL_PAST_DAYS)).isoformat(),
        "arrival_max": (ref + timedelta(days=ARRIVAL_FUTURE_DAYS)).isoformat(),
        "departure_max_global": (ref + timedelta(days=ARRIVAL_FUTURE_DAYS)).isoformat(),
        "max_stay_days": MAX_STAY_DAYS,
    }
