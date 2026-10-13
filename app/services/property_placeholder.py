"""Property / establishment shown on PDFs: the assigned apartment, or a placeholder until the host picks one."""

from sqlalchemy.orm import Session

from app.models import Apartment

PROPERTY_PLACEHOLDER = "waiting for dynamic assigning"
PLACEHOLDER_SLUG = "__dynamic_placeholder__"


def pdf_establishment_name() -> str:
    return PROPERTY_PLACEHOLDER


def pdf_establishment_address() -> str:
    return PROPERTY_PLACEHOLDER


def pdf_property_line() -> str:
    return PROPERTY_PLACEHOLDER


def is_placeholder(apartment: Apartment | None) -> bool:
    return apartment is None or apartment.slug == PLACEHOLDER_SLUG


def establishment_for(submission) -> tuple[str, str]:
    """(name, address) for the submission's PDFs."""
    apt = submission.apartment
    if is_placeholder(apt):
        return PROPERTY_PLACEHOLDER, PROPERTY_PLACEHOLDER
    return apt.name, (apt.address or "").strip() or apt.name


def get_or_create_placeholder_apartment(db: Session) -> Apartment:
    """Internal DB row only — not shown in admin."""
    apt = (
        db.query(Apartment)
        .filter(Apartment.slug == PLACEHOLDER_SLUG)
        .first()
    )
    if apt:
        return apt
    apt = Apartment(
        name=PROPERTY_PLACEHOLDER,
        address=PROPERTY_PLACEHOLDER,
        slug=PLACEHOLDER_SLUG,
        is_active=False,
        sort_order=-1,
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)
    return apt
