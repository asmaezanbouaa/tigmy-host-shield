"""Generate or refresh the single contract PDF of a submission."""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Document, Submission
from app.services.pdf_generator import generate_contract_pdf
from app.services.property_placeholder import establishment_for
from app.services.storage import absolute_path, unlink_if_exists

settings = get_settings()


def _write_contract(submission: Submission, signature_rel: str | None = None):
    name, address = establishment_for(submission)
    sig_full = absolute_path(signature_rel or submission.signature_path)
    filename = f"contrat_{submission.public_id}.pdf"
    full = settings.pdfs_path / filename
    generate_contract_pdf(submission, name, address, sig_full, full)
    return filename, str(full.relative_to(settings.storage_path.parent))


def regenerate_submission_pdfs(db: Session, submission: Submission) -> None:
    filename, rel = _write_contract(submission)
    doc = submission.document
    if doc:
        # Older submissions also had a separate fiche and rules PDF: the contract replaces both.
        for old in (doc.pdf_path, doc.rules_pdf_path):
            if old and old != rel:
                unlink_if_exists(old)
        doc.pdf_path, doc.filename = rel, filename
        doc.rules_pdf_path = doc.rules_filename = None
    else:
        db.add(Document(submission_id=submission.id, pdf_path=rel, filename=filename))


def create_submission_pdfs(db: Session, submission: Submission, signature_rel: str) -> Document:
    filename, rel = _write_contract(submission, signature_rel)
    doc = Document(submission_id=submission.id, pdf_path=rel, filename=filename)
    db.add(doc)
    return doc
