#!/usr/bin/env python3
"""ID documents, rules PDF path, registry meta, optional email."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import engine


def _column_exists(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _table_exists(inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def run_migrations():
    inspector = inspect(engine)

    with engine.begin() as conn:
        if _table_exists(inspector, "submissions"):
            for name, typedef in (
                ("id_document_path", "VARCHAR(512)"),
                ("id_document_verified_at", "DATETIME"),
            ):
                if not _column_exists(inspector, "submissions", name):
                    conn.execute(
                        text(f"ALTER TABLE submissions ADD COLUMN {name} {typedef}")
                    )

        if _table_exists(inspector, "documents"):
            for name, typedef in (
                ("rules_pdf_path", "VARCHAR(512)"),
                ("rules_filename", "VARCHAR(255)"),
            ):
                if not _column_exists(inspector, "documents", name):
                    conn.execute(
                        text(f"ALTER TABLE documents ADD COLUMN {name} {typedef}")
                    )

        if not _table_exists(inspector, "registry_meta"):
            conn.execute(
                text(
                    """
                    CREATE TABLE registry_meta (
                        key VARCHAR(64) PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
            )

    print("Migration v4 applied.")


if __name__ == "__main__":
    run_migrations()
