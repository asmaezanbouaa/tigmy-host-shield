#!/usr/bin/env python3
"""Initialize database, admin user, sample apartments, and shared guest link."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.services.admin_users import ensure_admin_users
from app.services.property_placeholder import get_or_create_placeholder_apartment
from app.services.public_urls import guest_register_url
from app.services.registration import get_or_create_shared_link
from app.services.storage import ensure_storage_dirs

settings = get_settings()


def main():
    ensure_storage_dirs()
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    try:
        from scripts.run_all_migrations import run_all_migrations

        run_all_migrations()
    except Exception as exc:
        print(f"Migration note: {exc}")

    db = SessionLocal()
    try:
        changes = ensure_admin_users(db)
        for note in changes:
            print(f"Admin user {note}")

        get_or_create_placeholder_apartment(db)
        get_or_create_shared_link(db)

        print("Guest registration link (share with guests):")
        print(guest_register_url())
    finally:
        db.close()

    print("Database initialized successfully.")


if __name__ == "__main__":
    main()
