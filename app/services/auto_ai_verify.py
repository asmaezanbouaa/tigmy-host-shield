"""Run AI verification on guest submit; auto-confirm when confidence is high enough."""

import logging
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Submission
from app.services.ai_verification import save_verification_result, verify_submission_id

logger = logging.getLogger("uvicorn.error")

# Never auto-confirm unless these match the ID scan, whatever the overall score.
CRITICAL_FIELDS = ("last_name", "id_document_number")


def run_auto_ai_verification(db: Session, submission: Submission) -> dict | None:
    """
    Compare form vs ID scan after submit.

    Mark as AI-approved only when confidence >= threshold AND the critical fields
    (last name, ID number) both match the scan. The submission stays "submitted"
    either way: the host confirms it after choosing the apartment.
    """
    settings = get_settings()
    if not settings.ai_verification_enabled or not settings.ai_auto_verify_on_submit:
        return None
    if not submission.id_document_path:
        return None

    try:
        result = verify_submission_id(submission)
    except Exception as exc:
        logger.warning(
            "Auto AI verification failed for %s: %s",
            submission.public_id,
            exc,
        )
        return None

    confidence = float(result.get("confidence") or 0)
    threshold = settings.ai_auto_confirm_threshold
    result["auto_checked"] = True
    result["auto_confirm_threshold"] = threshold

    statuses = {f.get("field"): f.get("status") for f in result.get("fields") or []}
    critical_ok = all(statuses.get(k) == "match" for k in CRITICAL_FIELDS)
    result["critical_fields_matched"] = critical_ok

    if confidence >= threshold and critical_ok:
        # AI approved the ID. The host still confirms after choosing the apartment.
        submission.ai_auto_confirmed = True
        result["auto_confirmed"] = True
        logger.info(
            "AI approved submission %s (confidence %.0f%%), waiting for apartment",
            submission.public_id,
            confidence * 100,
        )
    else:
        submission.ai_auto_confirmed = False
        result["auto_confirmed"] = False
        result["needs_review"] = True
        logger.info(
            "Submission %s needs manual review (AI confidence %.0f%%)",
            submission.public_id,
            confidence * 100,
        )

    save_verification_result(submission, result)
    db.flush()
    return result
