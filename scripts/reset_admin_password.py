#!/usr/bin/env python3
"""Reset admin password from .env (ADMIN_USERNAME / ADMIN_PASSWORD)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import SessionLocal
from app.models import AdminUser
from app.services.auth import hash_password

settings = get_settings()


def main():
    db = SessionLocal()
    try:
        admin = (
            db.query(AdminUser)
            .filter(AdminUser.username == settings.admin_username)
            .first()
        )
        if not admin:
            admin = AdminUser(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
            db.add(admin)
            print(f"Created admin: {settings.admin_username}")
        else:
            admin.password_hash = hash_password(settings.admin_password)
            print(f"Password updated for: {settings.admin_username}")
        db.commit()
        print("Use these credentials at /admin/login")
    finally:
        db.close()


if __name__ == "__main__":
    main()
