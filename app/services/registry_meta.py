"""Persistent registry counters (survive archive purges)."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import RegistryMeta

KEY_ARCHIVE_PURGED_TOTAL = "archive_purged_total"
KEY_ARCHIVE_LAST_PURGE_AT = "archive_last_purge_at"


def _get_row(db: Session, key: str) -> RegistryMeta | None:
    return db.query(RegistryMeta).filter(RegistryMeta.key == key).first()


def get_int(db: Session, key: str, default: int = 0) -> int:
    row = _get_row(db, key)
    if not row or not row.value.strip():
        return default
    try:
        return int(row.value)
    except ValueError:
        return default


def set_int(db: Session, key: str, value: int) -> None:
    row = _get_row(db, key)
    if row:
        row.value = str(value)
    else:
        db.add(RegistryMeta(key=key, value=str(value)))
    db.commit()


def get_iso_datetime(db: Session, key: str) -> datetime | None:
    row = _get_row(db, key)
    if not row or not row.value.strip():
        return None
    try:
        return datetime.fromisoformat(row.value.replace("Z", "+00:00"))
    except ValueError:
        return None


def set_iso_datetime(db: Session, key: str, when: datetime) -> None:
    row = _get_row(db, key)
    val = when.astimezone(timezone.utc).isoformat()
    if row:
        row.value = val
    else:
        db.add(RegistryMeta(key=key, value=val))
    db.commit()
