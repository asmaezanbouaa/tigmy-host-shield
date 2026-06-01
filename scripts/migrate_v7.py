#!/usr/bin/env python3
"""Add submissions.ai_auto_confirmed for AI auto-approval tracking."""

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
        if not _column_exists(inspector, "submissions", "ai_auto_confirmed"):
            conn.execute(
                text(
                    "ALTER TABLE submissions ADD COLUMN ai_auto_confirmed BOOLEAN NOT NULL DEFAULT 0"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_submissions_ai_auto_confirmed "
                    "ON submissions (ai_auto_confirmed)"
                )
            )

    print("Migration v7 applied (AI auto-confirm flag).")


if __name__ == "__main__":
    run_migrations()
