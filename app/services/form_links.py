from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import FormLink, FormLinkStatus
from app.services.tokens import generate_form_token

settings = get_settings()


def guest_url(token: str) -> str:
    base = settings.base_url.rstrip("/")
    return f"{base}/f/{token}"


def is_link_usable(link: FormLink) -> tuple[bool, str]:
    if link.status == FormLinkStatus.CANCELLED.value:
        return False, "This form link has been cancelled."
    if not link.is_shared and link.status == FormLinkStatus.SUBMITTED.value:
        return False, "This form has already been submitted."
    if link.status == FormLinkStatus.EXPIRED.value:
        return False, "This form link has expired."
    if link.expires_at:
        now = datetime.now(timezone.utc)
        exp = link.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            return False, "This form link has expired."
    return True, ""


def create_form_link(
    db: Session,
    property_address: str,
    guest_label: str | None = None,
    expiry_days: int | None = None,
    single_use: bool = True,
) -> FormLink:
    days = expiry_days if expiry_days is not None else settings.default_link_expiry_days
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    link = FormLink(
        token=generate_form_token(),
        property_address=property_address,
        guest_label=guest_label,
        expires_at=expires_at,
        single_use=single_use,
        status=FormLinkStatus.ACTIVE.value,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link
