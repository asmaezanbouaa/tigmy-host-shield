"""French display helpers: dates in Morocco time, status labels, amounts, WhatsApp links."""

from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from app.config import get_settings

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]
MONTHS_SHORT = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
WEEKDAYS_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

try:  # Morocco: UTC+1 (UTC+0 during Ramadan) — the tz database knows
    from zoneinfo import ZoneInfo

    _MOROCCO = ZoneInfo("Africa/Casablanca")
except Exception:  # pragma: no cover - tzdata missing
    _MOROCCO = timezone(timedelta(hours=1))

STATUS_LABELS = {
    "submitted": "À traiter",
    "confirmed": "Confirmé",
    "issue": "Problème",
    "archived": "Archivé",
    "cancelled": "Annulé",
}
AI_OVERALL = {"match": "Concordant", "partial": "Partiel", "mismatch": "Différent", "unclear": "Peu clair"}
AI_FIELD_STATUS = {"match": "Identique", "mismatch": "Différent", "missing": "Absent", "unclear": "Illisible"}
AI_FIELDS = {
    "last_name": "Nom", "first_name": "Prénom", "date_of_birth": "Date de naissance",
    "nationality": "Nationalité", "id_document_number": "N° de pièce",
}
PACK_STATE_LABELS = {"none": "Aucun pack", "active": "Actif", "exhausted": "Épuisé", "expired": "Expiré"}


def local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # the database stores UTC
    return dt.astimezone(_MOROCCO)


def fdate(dt) -> str:
    """12 oct. 2026"""
    d = local(dt) if isinstance(dt, datetime) else dt
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year}" if d else "—"


def fdatetime(dt) -> str:
    """12 oct. 2026 à 14:05"""
    d = local(dt)
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year} à {d:%H:%M}" if d else "—"


def fshort(d) -> str:
    """13 oct. (chart axis)"""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]}" if d else "—"


def fday(value) -> str:
    """'2026-10-16' -> '16 oct. 2026' (stay dates are stored as ISO text)."""
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value or "—")
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year}"


def fdate_long(dt) -> str:
    """12 octobre 2026"""
    d = local(dt) if isinstance(dt, datetime) else dt
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}" if d else "—"


def fmonth(year: int, month: int) -> str:
    return f"{MONTHS[month - 1].capitalize()} {year}"


def status_fr(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def dh(amount: int | float) -> str:
    """1 200"""
    return f"{int(amount):,}".replace(",", " ")


def per_fiche(price: int, fiches: int) -> str:
    """0,44"""
    return f"{price / fiches:.2f}".replace(".", ",") if fiches else "—"


def plural(n: int, one: str, many: str) -> str:
    return one if n in (0, 1) else many


def whatsapp_url(message: str = "") -> str:
    number = "".join(ch for ch in get_settings().support_whatsapp if ch.isdigit())
    if not number:
        return ""
    return f"https://wa.me/{number}" + (f"?text={quote(message)}" if message else "")


def register(env) -> None:
    env.filters.update({
        "fdate": fdate, "fshort": fshort, "fday": fday, "fdatetime": fdatetime, "fdate_long": fdate_long, "status_fr": status_fr, "dh": dh,
    })
    env.globals.update({
        "fmonth": fmonth, "per_fiche": per_fiche, "plural": plural, "wa": whatsapp_url,
        "AI_OVERALL": AI_OVERALL, "AI_FIELD_STATUS": AI_FIELD_STATUS, "AI_FIELDS": AI_FIELDS,
        "PACK_STATE_LABELS": PACK_STATE_LABELS, "WEEKDAYS_SHORT": WEEKDAYS_SHORT,
    })
