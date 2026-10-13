from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import AdminUser, HostSection
from app.services.auth import decode_access_token

settings = get_settings()


OWNER_VIEW_COOKIE = "owner_view_section"


def get_current_admin(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    owner_view: str | None = Cookie(default=None, alias=OWNER_VIEW_COOKIE),
) -> AdminUser:
    if not session_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    username = decode_access_token(session_token)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    admin = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active).first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    if not admin_can_sign_in(admin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Section is disabled")
    if admin.is_superadmin and owner_view:
        # Platform owner opened another section from the Sections page.
        admin.viewing_section = db.query(HostSection).filter(HostSection.public_id == owner_view).first()
    return admin


def admin_can_sign_in(admin: AdminUser) -> bool:
    """Section admins need an active section; the platform owner can always sign in."""
    if admin.is_superadmin:
        return admin.section_id is not None
    return admin.section is not None and admin.section.is_active


def get_superadmin(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    if not admin.is_superadmin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform owner only")
    return admin
