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

    Called on app startup so Railway redeploys always honor ADMIN_* variables.
    """
    updated: list[str] = []
    for username, password in admin_accounts_from_settings():
        admin = db.query(AdminUser).filter(AdminUser.username == username).first()
        if not admin:
            db.add(
                AdminUser(
                    username=username,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            updated.append(f"created:{username}")
            continue

        admin.is_active = True
        if sync_passwords:
            admin.password_hash = hash_password(password)
            updated.append(f"synced:{username}")
        else:
            updated.append(f"exists:{username}")

    if updated:
        db.commit()
    return updated
