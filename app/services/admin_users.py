"""Create or update admin users from environment variables (survives redeploys)."""

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import AdminUser
from app.services.auth import hash_password


def admin_accounts_from_settings(settings: Settings | None = None) -> list[tuple[str, str]]:
    """Return (username, password) pairs configured via env."""
    s = settings or get_settings()
    accounts: list[tuple[str, str]] = []

    primary = (s.admin_username or "").strip()
    if primary and s.admin_password:
        accounts.append((primary, s.admin_password))

    secondary = (s.admin_username_2 or "").strip()
    if secondary and s.admin_password_2:
        accounts.append((secondary, s.admin_password_2))

    return accounts


def ensure_admin_users(db: Session, *, sync_passwords: bool = True) -> list[str]:
    """
    Ensure every configured admin exists and passwords match env vars.
    The first env account (ADMIN_USERNAME) is the admin; ADMIN_USERNAME_2 is a host user of the default host.

    Called on app startup so Railway redeploys always honor ADMIN_* variables.
    """
    from app.services.sections import get_or_create_default_section

    updated: list[str] = []
    default_section = get_or_create_default_section(db)
    for index, (username, password) in enumerate(admin_accounts_from_settings()):
        # The first env admin (ADMIN_USERNAME) is the platform owner.
        is_owner = index == 0
        admin = db.query(AdminUser).filter(AdminUser.username == username).first()
        if not admin:
            db.add(
                AdminUser(
                    username=username,
                    password_hash=hash_password(password),
                    is_active=True,
                    is_superadmin=is_owner,
                    section_id=None if is_owner else default_section.id,
                )
            )
            updated.append(f"created:{username}")
            continue

        admin.is_active = True
        if is_owner:
            # The admin oversees every host and has no host of its own.
            admin.is_superadmin = True
            admin.section_id = None
        elif admin.section_id is None:
            admin.section_id = default_section.id
        if sync_passwords:
            admin.password_hash = hash_password(password)
            updated.append(f"synced:{username}")
        else:
            updated.append(f"exists:{username}")

    if updated:
        db.commit()
    return updated
