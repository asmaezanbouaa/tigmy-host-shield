#!/usr/bin/env python3
"""Upgrade existing SQLite DB to apartments + new submission fields."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import engine


def _column_exists(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def _rebuild_submissions_table(conn):
    """SQLite: replace submissions table to drop legacy columns (gender, etc.)."""
    conn.execute(text("PRAGMA foreign_keys=OFF"))
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS submissions_new (
            id INTEGER PRIMARY KEY,
            public_id VARCHAR(36) UNIQUE NOT NULL,
            form_link_id INTEGER,
            apartment_id INTEGER NOT NULL,
            last_name VARCHAR(128) NOT NULL,
            first_name VARCHAR(128) NOT NULL,
            nationality VARCHAR(128) NOT NULL,
            date_of_birth VARCHAR(16) NOT NULL,
            country_of_residence VARCHAR(128) NOT NULL,
            number_of_guests INTEGER DEFAULT 1,
            number_of_kids INTEGER DEFAULT 0,
            arrival_date VARCHAR(16) NOT NULL,
            departure_date VARCHAR(16) NOT NULL,
            id_document_type VARCHAR(64) NOT NULL,
            id_document_number VARCHAR(128) NOT NULL,
            accept_internal_rules BOOLEAN DEFAULT 0,
            accept_terms BOOLEAN DEFAULT 0,
            signature_path VARCHAR(512) NOT NULL,
            status VARCHAR(32) NOT NULL,
            ip_address VARCHAR(64),
            user_agent VARCHAR(512),
            submitted_at DATETIME
        )
        """
        )
    )
    conn.execute(
        text(
            """
        INSERT INTO submissions_new (
            id, public_id, form_link_id, apartment_id,
            last_name, first_name, nationality, date_of_birth,
            country_of_residence, number_of_guests, number_of_kids,
            arrival_date, departure_date, id_document_type, id_document_number,
            accept_internal_rules, accept_terms, signature_path, status,
            ip_address, user_agent, submitted_at
        )
        SELECT
            s.id, s.public_id, s.form_link_id,
            COALESCE(s.apartment_id, (SELECT id FROM apartments LIMIT 1)),
            s.last_name, s.first_name, s.nationality, s.date_of_birth,
            s.country_of_residence,
            COALESCE(s.number_of_guests, COALESCE(s.children_under_18, 0) + 1, 1),
            COALESCE(s.number_of_kids, s.children_under_18, 0),
            s.arrival_date, s.departure_date, s.id_document_type, s.id_document_number,
            COALESCE(s.accept_internal_rules, 0),
            COALESCE(s.accept_terms, 0),
            s.signature_path, s.status, s.ip_address, s.user_agent, s.submitted_at
        FROM submissions s
        """
        )
    )
    conn.execute(text("DROP TABLE submissions"))
    conn.execute(text("ALTER TABLE submissions_new RENAME TO submissions"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_submissions_public_id ON submissions (public_id)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_submissions_apartment_id ON submissions (apartment_id)"
        )
    )
    conn.execute(text("PRAGMA foreign_keys=ON"))


def run_migrations():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    with engine.begin() as conn:
        if "apartments" not in tables:
            conn.execute(
                text(
                    """
                CREATE TABLE apartments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id VARCHAR(36) UNIQUE NOT NULL,
                    name VARCHAR(128) NOT NULL,
                    address TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
                )
            )

        if "form_links" in tables and not _column_exists(inspector, "form_links", "is_shared"):
            conn.execute(
                text("ALTER TABLE form_links ADD COLUMN is_shared BOOLEAN DEFAULT 0")
            )

        if "submissions" not in tables:
            return

        legacy = _column_exists(inspector, "submissions", "gender")
        if legacy:
            if not _column_exists(inspector, "submissions", "apartment_id"):
                conn.execute(
                    text("ALTER TABLE submissions ADD COLUMN apartment_id INTEGER")
                )
            row = conn.execute(text("SELECT id FROM apartments LIMIT 1")).fetchone()
            if not row:
                import uuid

                pid = str(uuid.uuid4())
                conn.execute(
                    text(
                        "INSERT INTO apartments (public_id, name, address, is_active, sort_order) "
                        "VALUES (:pid, 'Default apartment', 'Update address in admin', 1, 0)"
                    ),
                    {"pid": pid},
                )
            _rebuild_submissions_table(conn)
        else:
            if not _column_exists(inspector, "submissions", "apartment_id"):
                conn.execute(
                    text("ALTER TABLE submissions ADD COLUMN apartment_id INTEGER")
                )
            if not _column_exists(inspector, "submissions", "number_of_guests"):
                conn.execute(
                    text(
                        "ALTER TABLE submissions ADD COLUMN number_of_guests INTEGER DEFAULT 1"
                    )
                )
            if not _column_exists(inspector, "submissions", "number_of_kids"):
                conn.execute(
                    text(
                        "ALTER TABLE submissions ADD COLUMN number_of_kids INTEGER DEFAULT 0"
                    )
                )

        conn.execute(
            text(
                "UPDATE form_links SET is_shared = 1, single_use = 0 "
                "WHERE guest_label = '__shared_registration__'"
            )
        )

    print("Migration v2 applied.")


if __name__ == "__main__":
    run_migrations()
