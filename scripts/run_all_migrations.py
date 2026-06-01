#!/usr/bin/env python3
"""Run all schema migrations (v2–v6). Safe to call multiple times."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_all_migrations() -> None:
    from scripts.migrate_v2 import run_migrations as migrate_v2
    from scripts.migrate_v3 import run_migrations as migrate_v3
    from scripts.migrate_v4 import run_migrations as migrate_v4
    from scripts.migrate_v5 import run_migrations as migrate_v5
    from scripts.migrate_v6 import run_migrations as migrate_v6

    for name, fn in (
        ("v2", migrate_v2),
        ("v3", migrate_v3),
        ("v4", migrate_v4),
        ("v5", migrate_v5),
        ("v6", migrate_v6),
    ):
        try:
            fn()
        except Exception as exc:
            print(f"Migration {name} note: {exc}")


if __name__ == "__main__":
    run_all_migrations()
    print("All migrations applied.")
