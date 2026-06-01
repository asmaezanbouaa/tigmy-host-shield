#!/usr/bin/env python3
"""Create an additional admin user (or reset password if username exists)."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import AdminUser
from app.services.auth import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an admin user.")
    parser.add_argument("username", help="Admin login username")
    parser.add_argument("password", help="Admin login password")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password
    if not username:
        print("Username cannot be empty.", file=sys.stderr)
        sys.exit(1)
    if len(password) < 4:
        print("Password must be at least 4 characters.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == username).first()
        if admin:
            admin.password_hash = hash_password(password)
            admin.is_active = True
            print(f"Updated password for admin: {username}")
        else:
            db.add(
                AdminUser(
                    username=username,
                    password_hash=hash_password(password),
                )
            )
            print(f"Created admin: {username}")
        db.commit()
        print("They can log in at /admin/login")
    finally:
        db.close()


if __name__ == "__main__":
    main()
