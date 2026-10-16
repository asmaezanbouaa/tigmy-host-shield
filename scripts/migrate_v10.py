#!/usr/bin/env python3
"""Packs and orders: create host_packs / pack_orders, and give every existing host a starting pack.

Existing hosts get the "Petite activité" pack (100 fiches, 2 months) with the registrations they already
have counted as used. Runs once per host: hosts that already own a pack are left alone.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, inspect

from app.database import Base, SessionLocal, engine


def run_migrations():
    import app.models  # noqa: F401  (register the tables)
    from app.models import HostPack, HostSection, Submission
    from app.services.packs import activate_pack

    tables = set(inspect(engine).get_table_names())
    for name in ("pack_orders", "host_packs"):  # pack_orders first: host_packs points to it
        if name not in tables:
            Base.metadata.tables[name].create(bind=engine)

    granted = 0
    with SessionLocal() as db:
        for section in db.query(HostSection).all():
            if db.query(HostPack.id).filter(HostPack.section_id == section.id).first():
                continue
            pack = activate_pack(db, section.id, "petite", source="admin")
            existing = db.query(func.count(Submission.id)).filter(Submission.section_id == section.id).scalar() or 0
            pack.fiches_used = min(existing, pack.fiches_total)
            granted += 1
        db.commit()
    print(f"Migration v10 applied (packs and orders; {granted} starting pack(s) granted).")


if __name__ == "__main__":
    run_migrations()
