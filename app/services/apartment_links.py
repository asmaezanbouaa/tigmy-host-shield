"""Apartment slugs and ?apt= URL resolution for listing-specific guest links."""

import re
import unicodedata

from sqlalchemy.orm import Session

from app.models import Apartment

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_name(name: str) -> str:
    """URL-safe slug from apartment name, e.g. 'Apartment 2' -> 'apartment-2'."""
    text = unicodedata.normalize("NFKD", (name or "").strip())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text[:64] or "apartment"


def ensure_unique_slug(db: Session, base: str, exclude_id: int | None = None) -> str:
    slug = base[:64] or "apartment"
    n = 0
    while True:
        candidate = slug if n == 0 else f"{slug[:58]}-{n}"
        q = db.query(Apartment).filter(Apartment.slug == candidate)
        if exclude_id is not None:
            q = q.filter(Apartment.id != exclude_id)
        if not q.first():
            return candidate
        n += 1


def assign_slug(apt: Apartment, db: Session) -> None:
    if apt.slug:
        return
    apt.slug = ensure_unique_slug(db, slugify_name(apt.name), exclude_id=apt.id)


def resolve_apartment_from_param(db: Session, apt_param: str) -> Apartment | None:
    """Match ?apt= by slug, public_id, or slugified name."""
    raw = (apt_param or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    apt = (
        db.query(Apartment)
        .filter(Apartment.is_active.is_(True), Apartment.slug == lowered)
        .first()
    )
    if apt:
        return apt

    apt = (
        db.query(Apartment)
        .filter(Apartment.is_active.is_(True), Apartment.public_id == raw)
        .first()
    )
    if apt:
        return apt

    for candidate in _active_apartments(db):
        if slugify_name(candidate.name) == lowered:
            return candidate
        if candidate.name.strip().lower() == lowered:
            return candidate
    return None


def _active_apartments(db: Session) -> list[Apartment]:
    return (
        db.query(Apartment)
        .filter(Apartment.is_active.is_(True))
        .order_by(Apartment.sort_order, Apartment.name)
        .all()
    )


def guest_url_with_apt(base_guest_url: str, apartment: Apartment) -> str:
    """Append ?apt=slug to shared registration URL."""
    slug = apartment.slug or slugify_name(apartment.name)
    sep = "&" if "?" in base_guest_url else "?"
    return f"{base_guest_url}{sep}apt={slug}"
