"""Host sections: each host business has its own admins, apartments, guest link and guests."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import AdminUser, Apartment, HostSection, Submission
from app.services.apartment_links import slugify_name
from app.services.auth import hash_password

MAX_ADMINS_PER_SECTION = 2
DEFAULT_SECTION_SLUG = "main"
DEFAULT_SECTION_NAME = "Hôte principal"
MIN_PASSWORD_LENGTH = 10


def unique_section_slug(db: Session, name: str, exclude_id: int | None = None) -> str:
    base = slugify_name(name)[:56] or "section"
    n = 0
    while True:
        candidate = base if n == 0 else f"{base}-{n}"
        q = db.query(HostSection).filter(HostSection.slug == candidate)
        if exclude_id is not None:
            q = q.filter(HostSection.id != exclude_id)
        if not q.first():
            return candidate
        n += 1


def get_or_create_default_section(db: Session) -> HostSection:
    """Host opened by the plain /register link: the "main" host, else the oldest host."""
    section = (
        db.query(HostSection).filter(HostSection.slug == DEFAULT_SECTION_SLUG).first()
        or db.query(HostSection).order_by(HostSection.id).first()
    )
    if section:
        return section
    section = HostSection(name=DEFAULT_SECTION_NAME, slug=DEFAULT_SECTION_SLUG, is_active=True)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


def section_by_slug(db: Session, slug: str) -> HostSection | None:
    return (
        db.query(HostSection)
        .filter(HostSection.slug == (slug or "").strip().lower(), HostSection.is_active.is_(True))
        .first()
    )


def section_admins(db: Session, section_id: int) -> list[AdminUser]:
    return (
        db.query(AdminUser)
        .filter(AdminUser.section_id == section_id)
        .order_by(AdminUser.created_at, AdminUser.id)
        .all()
    )


def section_apartments(db: Session, section_id: int, *, active_only: bool = False) -> list[Apartment]:
    q = db.query(Apartment).filter(Apartment.section_id == section_id)
    if active_only:
        q = q.filter(Apartment.is_active.is_(True))
    return q.order_by(Apartment.sort_order, Apartment.name).all()


def section_stats(db: Session, section_id: int) -> dict[str, int]:
    return {
        "admins": db.query(func.count(AdminUser.id)).filter(AdminUser.section_id == section_id).scalar() or 0,
        "apartments": db.query(func.count(Apartment.id))
        .filter(Apartment.section_id == section_id, Apartment.is_active.is_(True))
        .scalar()
        or 0,
        "guests": db.query(func.count(Submission.id)).filter(Submission.section_id == section_id).scalar() or 0,
    }


def validate_new_admin(db: Session, username: str, password: str) -> str | None:
    """Return an error message, or None when the username/password are acceptable."""
    if not username or len(username) < 3 or len(username) > 64:
        return "L'identifiant doit contenir 3 à 64 caractères."
    if not all(c.isalnum() or c in "._-" for c in username):
        return "L'identifiant ne peut contenir que des lettres, chiffres, points, tirets et underscores."
    if db.query(AdminUser).filter(func.lower(AdminUser.username) == username.lower()).first():
        return f"L'identifiant « {username} » est déjà utilisé."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères."
    return None


def add_section_admin(db: Session, section: HostSection, username: str, password: str) -> AdminUser:
    admin = AdminUser(
        username=username,
        password_hash=hash_password(password),
        is_active=True,
        is_superadmin=False,
        section_id=section.id,
    )
    db.add(admin)
    db.flush()
    return admin
