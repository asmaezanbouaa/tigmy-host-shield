#!/usr/bin/env python3
"""Add (or remove with --remove) fake demo sections, apartments and guests.

Demo admin usernames and their shared password are written to data/demo_accounts.txt.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.services.demo_data import ACCOUNTS_FILE, remove_demo_data, seed_demo_data


def main() -> None:
    with SessionLocal() as db:
        if "--remove" in sys.argv:
            sections, guests = remove_demo_data(db)
            print(f"Removed {sections} demo section(s) and {guests} demo guest record(s).")
            return
        result = seed_demo_data(db)
        if not result["sections"]:
            print("Demo data is already there. Run with --remove first to recreate it.")
            return
        print(f"Added {result['sections']} demo sections with {result['guests']} demo guests.")
        print(f"Demo admin logins are in {ACCOUNTS_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
