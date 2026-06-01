#!/usr/bin/env python3
"""AI verification result storage on submissions."""

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
        for name, typedef in (
            ("ai_verification_json", "TEXT"),
            ("ai_verification_at", "DATETIME"),
        ):
            if not _column_exists(inspector, "submissions", name):
                conn.execute(
                    text(f"ALTER TABLE submissions ADD COLUMN {name} {typedef}")
                )

    print("Migration v5 applied.")


if __name__ == "__main__":
    run_migrations()
