"""Public URLs for guests and admin (always from BASE_URL in .env)."""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.services.form_links import guest_url
from app.services.registration import get_or_create_shared_link

settings = get_settings()


def site_base() -> str:
    return settings.base_url.rstrip("/")


def guest_register_url() -> str:
    """Main link to share with guests (redirects to the active form)."""
    return f"{site_base()}/register"


def guest_form_url(token: str) -> str:
    return guest_url(token)


def admin_login_url() -> str:
    return f"{site_base()}/admin/login"


def admin_share_url() -> str:
    return f"{site_base()}/admin/share"


def shared_guest_form_url(db: Session) -> str:
    """Direct form URL with token (same as register after redirect)."""
    link = get_or_create_shared_link(db)
    return guest_form_url(link.token)
