#!/usr/bin/env python3
"""Create a host (section) with one user and the welcome pack.

Usage:  HOST_PASSWORD='...' python scripts/create_host.py "Nom de l'hôte" identifiant "Adresse de l'hôte"
The password is read from the environment so it never lands in shell history or the repo.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import HostSection
from app.services.registration import get_or_create_shared_link
from app.services.packs import grant_trial
from app.services.sections import add_section_admin, unique_section_slug, validate_new_admin


def main() -> None:
    if len(sys.argv) != 4 or not os.environ.get("HOST_PASSWORD"):
        sys.exit(__doc__)
    name, username, address, password = sys.argv[1], sys.argv[2], sys.argv[3], os.environ["HOST_PASSWORD"]
    db = SessionLocal()
    try:
        err = validate_new_admin(db, username, password)
        if err:
            sys.exit(err)
        section = HostSection(name=name, slug=unique_section_slug(db, name), is_active=True, address=address)
        db.add(section)
        db.flush()
        add_section_admin(db, section, username, password)
        grant_trial(db, section.id)
        db.commit()
        get_or_create_shared_link(db, section.id)
        print(f"OK  hôte « {name} » ({section.slug}), utilisateur {username}, pack de bienvenue activé")
    finally:
        db.close()


if __name__ == "__main__":
    main()
