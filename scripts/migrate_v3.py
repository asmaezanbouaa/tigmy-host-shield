#!/usr/bin/env python3
"""Add email + workflow columns to submissions."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import engine


def _column_exists(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def run_migrations():
    inspector = inspect(engine)
    if "submissions" not in inspector.get_table_names():
        return

    with engine.begin() as conn:
        cols = [
            ("email", "VARCHAR(255) NOT NULL DEFAULT ''"),
            ("admin_notes", "TEXT"),
            ("issue_message", "TEXT"),
            ("issue_email_sent_at", "DATETIME"),
            ("confirmed_at", "DATETIME"),
            ("archived_at", "DATETIME"),
        ]
        for name, typedef in cols:
            if not _column_exists(inspector, "submissions", name):
                conn.execute(text(f"ALTER TABLE submissions ADD COLUMN {name} {typedef}"))

        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_submissions_email ON submissions (email)"
            )
        )

    print("Migration v3 applied.")


if __name__ == "__main__":
    run_migrations()
