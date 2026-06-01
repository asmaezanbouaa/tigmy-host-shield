#!/usr/bin/env python3
"""Reset admin password from .env (ADMIN_USERNAME / ADMIN_PASSWORD)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.admin_users import ensure_admin_users


def main():
    db = SessionLocal()
    try:
        for note in ensure_admin_users(db):
            print(note)
        print("Use these credentials at /admin/login")
    finally:
        db.close()


if __name__ == "__main__":
    main()
