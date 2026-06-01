#!/usr/bin/env python3
"""Regenerate all submission PDFs (e.g. after coat-of-arms asset update)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import Submission
from app.services.submission_pdfs import regenerate_submission_pdfs


def main() -> None:
    db = SessionLocal()
    try:
        subs = db.query(Submission).order_by(Submission.id).all()
        if not subs:
            print("No submissions found.")
            return
        for sub in subs:
            regenerate_submission_pdfs(db, sub)
            print(f"OK  {sub.public_id}")
        db.commit()
        print(f"Done — {len(subs)} submission(s) updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
