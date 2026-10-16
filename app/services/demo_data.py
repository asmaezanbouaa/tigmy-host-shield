"""Fake host sections, apartments and guests for trying the platform. Everything uses the "demo-" slug prefix."""

import io
import json
import random
import secrets
import string
from datetime import date, datetime, time, timedelta, timezone

from PIL import Image, ImageDraw
from sqlalchemy.orm import Session, joinedload

from app.config import PROJECT_ROOT, get_settings
from app.models import AdminUser, Apartment, FormLink, HostPack, HostSection, PackOrder, Submission, SubmissionStatus
from app.services.packs import activate_pack
from app.services.apartment_links import ensure_unique_slug, slugify_name
from app.services.auth import hash_password
from app.services.property_placeholder import get_or_create_placeholder_apartment
from app.services.registration import get_or_create_shared_link
from app.services.storage import ensure_storage_dirs, save_id_document
from app.services.submission_pdfs import create_submission_pdfs
from app.services.submissions import permanently_delete_submission

DEMO_SLUG_PREFIX = "demo-"
ACCOUNTS_FILE = PROJECT_ROOT / "data" / "demo_accounts.txt"

# name, slug suffix, apartments (name, address, MAD/night), guest count,
# status weights (confirmed, pending review, AI approved awaiting apartment, issue, archived), AI approval rate
DEMO_SECTIONS = [
    (
        "Demo · Riad Atlas — Marrakech", "atlas",
        [
            ("Riad Atlas — Suite Majorelle", "14 Derb Sidi Bouloukat, Médina, Marrakech", 1450),
            ("Riad Atlas — Chambre Koutoubia", "14 Derb Sidi Bouloukat, Médina, Marrakech", 890),
            ("Atlas Garden Villa", "Route de l'Ourika km 9, Marrakech", 2600),
        ],
        18, (55, 10, 15, 5, 15), 0.78,
    ),
    (
        "Demo · Dar Mogador — Essaouira", "mogador",
        [
            ("Dar Mogador — Ocean View", "5 Rue de la Skala, Essaouira", 980),
            ("Dar Mogador — Patio Room", "5 Rue de la Skala, Essaouira", 620),
        ],
        9, (35, 30, 10, 15, 10), 0.45,
    ),
    (
        "Demo · Kasbah Souss — Agadir", "souss",
        [
            ("Kasbah Souss — Apt 1", "Bd du 20 Août, Founty, Agadir", 700),
            ("Kasbah Souss — Apt 2", "Bd du 20 Août, Founty, Agadir", 750),
            ("Taghazout Surf Loft", "Rue Principale, Taghazout", 1100),
            ("Imsouane Beach Studio", "Baie d'Imsouane, Imsouane", 540),
        ],
        24, (60, 8, 12, 4, 16), 0.88,
    ),
    (
        "Demo · Médina Blue — Tanger", "tanger",
        [
            ("Médina Blue — Kasbah Terrace", "22 Rue Ben Abbou, Kasbah, Tanger", 820),
            ("Cap Spartel House", "Route du Cap Spartel, Tanger", 1900),
        ],
        12, (40, 25, 15, 10, 10), 0.6,
    ),
]

DEMO_PACKS = {"atlas": "moyenne", "mogador": "petite", "souss": "grande", "tanger": "petite"}

# nationality (as guests type it on the French form), country, first names, last names
PEOPLE = [
    ("Marocaine", "Maroc", ["Youssef", "Salma", "Amine", "Khadija", "Omar", "Imane", "Hamza", "Nora"],
     ["El Amrani", "Benjelloun", "Tazi", "Alaoui", "Berrada", "Chraibi", "Idrissi"]),
    ("Française", "France", ["Camille", "Louis", "Chloé", "Hugo", "Léa", "Mathis"],
     ["Martin", "Bernard", "Dubois", "Moreau", "Laurent", "Lefèvre"]),
    ("Espagnole", "Espagne", ["Lucía", "Javier", "Carmen", "Pablo", "Marta"],
     ["García", "Fernández", "López", "Martínez", "Ruiz"]),
    ("Britannique", "Royaume-Uni", ["Oliver", "Emily", "James", "Sophie", "Harry"],
     ["Smith", "Taylor", "Brown", "Wilson", "Evans"]),
    ("Allemande", "Allemagne", ["Lukas", "Anna", "Felix", "Lena", "Jonas"],
     ["Müller", "Schmidt", "Schneider", "Fischer", "Weber"]),
    ("Américaine", "États-Unis", ["Ethan", "Olivia", "Noah", "Ava"], ["Johnson", "Williams", "Miller", "Davis"]),
    ("Italienne", "Italie", ["Giulia", "Marco", "Sofia", "Luca"], ["Rossi", "Russo", "Ferrari", "Esposito"]),
    ("Néerlandaise", "Pays-Bas", ["Daan", "Sanne", "Bram"], ["de Vries", "Jansen", "Bakker"]),
]
NATIONALITY_WEIGHTS = [30, 22, 12, 10, 9, 7, 6, 4]
ID_TYPES = ["Passeport / Passport", "Carte d'identité / ID card", "Permis de conduire / Driving licence"]
STATUS_KEYS = ["confirmed", "pending", "ai_awaiting", "issue", "archived"]
FIELDS = ["last_name", "first_name", "date_of_birth", "nationality", "id_document_number"]


def has_demo_data(db: Session) -> bool:
    return db.query(HostSection).filter(HostSection.slug.startswith(DEMO_SLUG_PREFIX)).first() is not None


def _signature_png(rng: random.Random) -> bytes:
    im = Image.new("RGBA", (600, 200), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    x, y = 40, 120
    points = []
    for _ in range(26):
        x += rng.randint(12, 24)
        y = max(40, min(170, y + rng.randint(-35, 35)))
        points.append((x, y))
    d.line([(40, 120)] + points, fill=(26, 26, 46, 255), width=4, joint="curve")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _id_scan_jpg(first: str, last: str, number: str, nationality: str) -> bytes:
    im = Image.new("RGB", (860, 540), (214, 222, 234))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 860, 90], fill=(46, 71, 120))
    d.text((30, 30), "SPECIMEN - DEMO IDENTITY DOCUMENT", fill="white")
    d.rectangle([40, 130, 260, 410], fill=(240, 240, 240), outline=(150, 150, 150))
    for i, (k, v) in enumerate(
        [("Surname", last.upper()), ("Given names", first), ("Nationality", nationality), ("Document no.", number)]
    ):
        d.text((300, 140 + i * 60), k, fill=(90, 90, 110))
        d.text((300, 162 + i * 60), v, fill=(20, 20, 40))
    d.text((40, 470), f"P<DEMO<{last.upper()}<<{first.upper()}<<<<<<<<<<<<", fill=(40, 40, 60))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _ai_result(rng: random.Random, approved: bool) -> dict:
    if approved:
        statuses = ["match"] * 5
        if rng.random() < 0.3:
            statuses[rng.choice([2, 3])] = "unclear"
    else:
        statuses = [rng.choice(["match", "mismatch", "unclear", "missing"]) for _ in FIELDS]
        statuses[4] = rng.choice(["mismatch", "unclear"])
    matched = statuses.count("match")
    overall = "match" if matched == 5 else ("partial" if matched else "mismatch")
    return {
        "overall": overall,
        "confidence": round(matched / 5, 2),
        "summary": f"Demo check: {matched}/5 fields matched the ID scan.",
        "fields": [{"field": f, "form_value": "", "id_value": "", "status": s} for f, s in zip(FIELDS, statuses)],
        "auto_checked": True,
        "auto_confirmed": approved,
    }


def seed_demo_data(db: Session) -> dict:
    """Create the demo sections. Returns {"sections", "guests", "password"}; no-op if present."""
    if has_demo_data(db):
        return {"sections": 0, "guests": 0, "password": None}

    settings = get_settings()
    ensure_storage_dirs()
    rng = random.Random(20261013)
    placeholder = get_or_create_placeholder_apartment(db)
    password = "Demo-" + "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
    pw_hash = hash_password(password)
    now = datetime.now(timezone.utc)
    today = now.date()
    accounts = []
    guest_total = 0

    for name, key, apts, n_guests, weights, ai_rate in DEMO_SECTIONS:
        section = HostSection(name=name, slug=f"{DEMO_SLUG_PREFIX}{key}", is_active=True)
        db.add(section)
        db.flush()
        for i in (1, 2):
            username = f"demo_{key}_{i}"
            db.add(
                AdminUser(
                    username=username,
                    password_hash=pw_hash,
                    is_active=True,
                    section_id=section.id,
                    last_login_at=now - timedelta(hours=rng.randint(1, 240)) if rng.random() < 0.8 else None,
                )
            )
            accounts.append((name, username))
        apartments = []
        for apt_name, address, _rate in apts:
            apt = Apartment(section_id=section.id, name=apt_name, address=address, is_active=True)
            apt.slug = ensure_unique_slug(db, slugify_name(f"{section.slug}-{apt_name}"))
            db.add(apt)
            apartments.append(apt)
        db.flush()
        link = get_or_create_shared_link(db, section.id)
        pack = activate_pack(db, section.id, DEMO_PACKS[key], source="admin")

        for _ in range(n_guests):
            nat, country, firsts, lasts = rng.choices(PEOPLE, weights=NATIONALITY_WEIGHTS)[0]
            first, last = rng.choice(firsts), rng.choice(lasts)
            kind = rng.choices(STATUS_KEYS, weights=weights)[0]
            submitted = now - timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            if kind == "archived":
                arrival = submitted.date() - timedelta(days=rng.randint(20, 60))
                submitted = datetime.combine(arrival - timedelta(days=rng.randint(1, 5)), time(10), tzinfo=timezone.utc)
            else:
                arrival = submitted.date() + timedelta(days=rng.randint(0, 25))
            nights = rng.choices([1, 2, 3, 4, 5, 7, 10], weights=[8, 18, 22, 18, 14, 12, 8])[0]
            guests = rng.choices([1, 2, 3, 4, 5], weights=[20, 45, 15, 15, 5])[0]
            number = f"{rng.choice(string.ascii_uppercase)}{rng.choice(string.ascii_uppercase)}{rng.randint(100000, 999999)}"
            dob = date(rng.randint(1958, 2004), rng.randint(1, 12), rng.randint(1, 28))

            sub = Submission(
                form_link_id=link.id,
                section_id=section.id,
                apartment_id=placeholder.id,
                last_name=last,
                first_name=first,
                nationality=nat,
                date_of_birth=dob.isoformat(),
                country_of_residence=country,
                number_of_guests=guests,
                number_of_kids=rng.randint(0, max(guests - 2, 0)),
                arrival_date=arrival.isoformat(),
                departure_date=(arrival + timedelta(days=nights)).isoformat(),
                id_document_type=rng.choice(ID_TYPES),
                id_document_number=number,
                accept_internal_rules=True,
                accept_terms=True,
                signature_path="",
                status=SubmissionStatus.SUBMITTED.value,
                ip_address="demo",
                user_agent="demo data",
                submitted_at=submitted,
            )
            db.add(sub)
            db.flush()

            sig_path = settings.signatures_path / f"{sub.public_id}_demo.png"
            sig_path.write_bytes(_signature_png(rng))
            sub.signature_path = str(sig_path.relative_to(settings.storage_path.parent))

            ai_checked = kind != "archived" or rng.random() < 0.5
            approved = kind == "ai_awaiting" or (kind == "confirmed" and rng.random() < ai_rate)
            if kind in ("pending", "issue"):
                approved = False
            if ai_checked:
                sub.ai_verification_json = json.dumps(_ai_result(rng, approved), ensure_ascii=False)
                sub.ai_verification_at = submitted + timedelta(seconds=rng.randint(4, 40))
                sub.ai_auto_confirmed = approved

            if kind in ("pending", "ai_awaiting"):
                sub.id_document_path = save_id_document(_id_scan_jpg(first, last, number, nat), "id.jpg", sub.public_id)
            if kind in ("confirmed", "archived") or (kind == "issue" and rng.random() < 0.5):
                sub.apartment_id = rng.choice(apartments).id
            if kind == "confirmed":
                sub.status = SubmissionStatus.CONFIRMED.value
                sub.confirmed_at = submitted + timedelta(hours=rng.randint(1, 30))
            elif kind == "issue":
                sub.status = SubmissionStatus.ISSUE.value
                sub.admin_notes = "Demo: ID number on the form does not match the scan."
            elif kind == "archived":
                sub.status = SubmissionStatus.ARCHIVED.value
                sub.confirmed_at = submitted + timedelta(hours=6)
                sub.archived_at = datetime.combine(arrival + timedelta(days=nights + 3), time(9), tzinfo=timezone.utc)

            db.flush()
            db.refresh(sub, ["apartment"])
            create_submission_pdfs(db, sub, sub.signature_path)
            guest_total += 1
        pack.fiches_used = n_guests
        db.commit()

    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "Demo admin accounts (fake data - remove from Platform stats > Remove demo data)",
        f"Password for every demo account: {password}",
        "",
    ] + [f"{section}: {username}" for section, username in accounts]
    ACCOUNTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ACCOUNTS_FILE.chmod(0o600)
    return {"sections": len(DEMO_SECTIONS), "guests": guest_total, "password": password}


def remove_demo_data(db: Session) -> tuple[int, int]:
    """Delete every demo section with its admins, apartments, links, guests and files."""
    sections = db.query(HostSection).filter(HostSection.slug.startswith(DEMO_SLUG_PREFIX)).all()
    guests = 0
    for section in sections:
        subs = (
            db.query(Submission)
            .options(joinedload(Submission.document))
            .filter(Submission.section_id == section.id)
            .all()
        )
        for sub in subs:
            permanently_delete_submission(db, sub)
            guests += 1
        db.query(HostPack).filter(HostPack.section_id == section.id).delete()
        db.query(PackOrder).filter(PackOrder.section_id == section.id).delete()
        db.query(AdminUser).filter(AdminUser.section_id == section.id).delete()
        db.query(Apartment).filter(Apartment.section_id == section.id).delete()
        db.query(FormLink).filter(FormLink.section_id == section.id).delete()
        db.delete(section)
        db.commit()
    if ACCOUNTS_FILE.exists():
        ACCOUNTS_FILE.unlink()
    return len(sections), guests
