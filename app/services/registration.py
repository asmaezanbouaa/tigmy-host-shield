"""Shared guest registration link — one URL for all clients."""

from sqlalchemy.orm import Session

from app.models import FormLink, FormLinkStatus
from app.services.form_links import guest_url
from app.services.tokens import generate_form_token

SHARED_LABEL = "__shared_registration__"


def get_or_create_shared_link(db: Session) -> FormLink:
    link = (
        db.query(FormLink)
        .filter(FormLink.is_shared.is_(True), FormLink.status == FormLinkStatus.ACTIVE.value)
        .first()
    )
    if link:
        return link

    link = FormLink(
        token=generate_form_token(),
        property_address="",
        guest_label=SHARED_LABEL,
        is_shared=True,
        single_use=False,
        expires_at=None,
        status=FormLinkStatus.ACTIVE.value,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def shared_guest_url(db: Session) -> str:
    return guest_url(get_or_create_shared_link(db).token)
