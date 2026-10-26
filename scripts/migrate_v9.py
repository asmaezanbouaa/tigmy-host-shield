#!/usr/bin/env python3
"""apartments.nightly_rate and admin_users.last_login_at (owner statistics)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import engine


def add_columns():
    """Schema only; runs before the older migrations, which load these tables through the ORM."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    def missing(table: str, column: str) -> bool:
        return table in tables and column not in {c["name"] for c in inspector.get_columns(table)}

    with engine.begin() as conn:
        if missing("apartments", "nightly_rate"):
            conn.execute(text("ALTER TABLE apartments ADD COLUMN nightly_rate INTEGER"))
        if missing("host_sections", "legal_info"):
            conn.execute(text("ALTER TABLE host_sections ADD COLUMN legal_info TEXT"))
        if missing("admin_users", "last_login_at"):
            conn.execute(text("ALTER TABLE admin_users ADD COLUMN last_login_at DATETIME"))


if __name__ == "__main__":
    add_columns()
    print("Migration v9 applied (nightly rate, last login).")
