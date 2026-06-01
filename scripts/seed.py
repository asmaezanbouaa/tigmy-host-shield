#!/usr/bin/env python3
"""Print the shared guest registration link."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.registration import shared_guest_url


def main():
    db = SessionLocal()
    try:
        print("Guest registration link (send to clients):")
        print(shared_guest_url(db))
        print("\nShort URL: /register")
    finally:
        db.close()


if __name__ == "__main__":
    main()
