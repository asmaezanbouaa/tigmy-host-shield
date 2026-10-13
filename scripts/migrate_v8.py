#!/usr/bin/env python3
"""Host sections: section_id on admins, apartments, links and submissions; superadmin flag.

Existing data moves into a default "Main section" so nothing is lost.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect, text

from app.database import Base, engine


def _column_exists(inspector, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspector.get_columns(table)}


def add_columns():
    """Schema part. Runs before the older migrations, which load these tables through the ORM."""
    import app.models  # noqa: F401  (register HostSection table)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "host_sections" not in tables:
        Base.metadata.tables["host_sections"].create(bind=engine)

    with engine.begin() as conn:
        for table in ("admin_users", "apartments", "form_links", "submissions"):
            if table in tables and not _column_exists(inspector, table, "section_id"):
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN section_id INTEGER REFERENCES host_sections(id)"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_section_id ON {table} (section_id)"))
        if "admin_users" in tables and not _column_exists(inspector, "admin_users", "is_superadmin"):
            conn.execute(text("ALTER TABLE admin_users ADD COLUMN is_superadmin BOOLEAN NOT NULL DEFAULT 0"))


def run_migrations():
    add_columns()

    from app.database import SessionLocal
    from app.models import AdminUser, Apartment, FormLink, RegistryMeta, Submission
    from app.services.property_placeholder import PLACEHOLDER_SLUG
    from app.services.registry_meta import KEY_ARCHIVE_LAST_PURGE_AT, KEY_ARCHIVE_PURGED_TOTAL, section_key
    from app.services.sections import get_or_create_default_section

    with SessionLocal() as db:
        default = get_or_create_default_section(db)
        sid = default.id

        db.query(Submission).filter(Submission.section_id.is_(None)).update({"section_id": sid})
        db.query(FormLink).filter(FormLink.section_id.is_(None)).update({"section_id": sid})
        db.query(Apartment).filter(
            Apartment.section_id.is_(None), Apartment.slug != PLACEHOLDER_SLUG
        ).update({"section_id": sid}, synchronize_session=False)
        db.query(AdminUser).filter(
            AdminUser.section_id.is_(None), AdminUser.is_superadmin.is_(False)
        ).update({"section_id": sid})

        # Archive counters were global; they now belong to the default section.
        for key in (KEY_ARCHIVE_PURGED_TOTAL, KEY_ARCHIVE_LAST_PURGE_AT):
            old = db.query(RegistryMeta).filter(RegistryMeta.key == key).first()
            new_key = section_key(key, sid)
            if old and not db.query(RegistryMeta).filter(RegistryMeta.key == new_key).first():
                db.add(RegistryMeta(key=new_key, value=old.value))
        db.commit()

    print("Migration v8 applied (host sections).")


if __name__ == "__main__":
    run_migrations()
