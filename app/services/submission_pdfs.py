"""Generate or refresh both PDFs for a submission."""

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, Submission
from app.services.pdf_assets import ensure_fiche_banner, ensure_rules_banner
from app.services.pdf_generator import generate_fiche_pdf, generate_rules_pdf
from app.services.property_placeholder import (
    pdf_establishment_address,
    pdf_establishment_name,
    pdf_property_line,
)
from app.services.storage import absolute_path

settings = get_settings()


def regenerate_submission_pdfs(db: Session, submission: Submission) -> None:
    ensure_fiche_banner()
    ensure_rules_banner()
    name = pdf_establishment_name()
    address = pdf_establishment_address()
    property_line = pdf_property_line()
    sig_full = absolute_path(submission.signature_path)

    fiche_name = f"fiche_{submission.public_id}.pdf"
    rules_name = f"reglement_{submission.public_id}.pdf"
    fiche_full = settings.pdfs_path / fiche_name
    rules_full = settings.pdfs_path / rules_name

    generate_fiche_pdf(submission, property_line, name, sig_full, fiche_full)
    generate_rules_pdf(submission, name, address, sig_full, rules_full)

    fiche_rel = str(fiche_full.relative_to(settings.storage_path.parent))
    rules_rel = str(rules_full.relative_to(settings.storage_path.parent))

    if submission.document:
        submission.document.pdf_path = fiche_rel
        submission.document.filename = fiche_name
        submission.document.rules_pdf_path = rules_rel
        submission.document.rules_filename = rules_name
    else:
        db.add(
            Document(
                submission_id=submission.id,
                pdf_path=fiche_rel,
                filename=fiche_name,
                rules_pdf_path=rules_rel,
                rules_filename=rules_name,
            )
        )


def create_submission_pdfs(
    db: Session,
    submission: Submission,
    signature_rel: str,
) -> Document:
    ensure_fiche_banner()
    ensure_rules_banner()
    name = pdf_establishment_name()
    address = pdf_establishment_address()
    property_line = pdf_property_line()
    sig_full = absolute_path(signature_rel)
    fiche_name = f"fiche_{submission.public_id}.pdf"
    rules_name = f"reglement_{submission.public_id}.pdf"
    fiche_full = settings.pdfs_path / fiche_name
    rules_full = settings.pdfs_path / rules_name

    generate_fiche_pdf(submission, property_line, name, sig_full, fiche_full)
    generate_rules_pdf(submission, name, address, sig_full, rules_full)

    doc = Document(
        submission_id=submission.id,
        pdf_path=str(fiche_full.relative_to(settings.storage_path.parent)),
        filename=fiche_name,
        rules_pdf_path=str(rules_full.relative_to(settings.storage_path.parent)),
        rules_filename=rules_name,
    )
    db.add(doc)
    return doc
