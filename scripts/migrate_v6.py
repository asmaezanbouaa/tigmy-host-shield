#!/usr/bin/env python3
"""Add apartment.slug for ?apt= guest links (one URL per Airbnb listing)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import SessionLocal, engine
from app.models import Apartment
from app.services.apartment_links import assign_slug, slugify_name


def _column_exists(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def run_migrations():
    inspector = inspect(engine)
    if "apartments" not in inspector.get_table_names():
        return

    with engine.begin() as conn:
        if not _column_exists(inspector, "apartments", "slug"):
            conn.execute(text("ALTER TABLE apartments ADD COLUMN slug VARCHAR(64)"))
            conn.execute(
                text("CREATE UNIQUE INDEX IF NOT EXISTS ix_apartments_slug ON apartments (slug)")
            )

    db = SessionLocal()
    try:
        for apt in db.query(Apartment).order_by(Apartment.id).all():
            if not apt.slug:
                assign_slug(apt, db)
        db.commit()
    finally:
        db.close()

    print("Migration v6 applied (apartment slugs).")


if __name__ == "__main__":
    run_migrations()
