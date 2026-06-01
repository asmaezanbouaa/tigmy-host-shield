#!/usr/bin/env python3
"""Print final guest and admin URLs from .env BASE_URL."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import SessionLocal
from app.services.public_urls import (
    admin_login_url,
    admin_share_url,
    guest_register_url,
    shared_guest_form_url,
)

if __name__ == "__main__":
    get_settings.cache_clear()
    settings = get_settings()
    db = SessionLocal()
    try:
        print("BASE_URL:", settings.base_url)
        print()
        print("Guest (share with Airbnb guests):")
        print(" ", guest_register_url())
        print()
        print("Guest direct form:")
        print(" ", shared_guest_form_url(db))
        print()
        print("Admin login:")
        print(" ", admin_login_url())
        print()
        print("Admin share page (copy link + QR):")
        print(" ", admin_share_url())
    finally:
        db.close()
