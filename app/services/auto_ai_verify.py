"""Run AI verification on guest submit; auto-confirm when confidence is high enough."""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Submission, SubmissionStatus
from app.services.ai_verification import save_verification_result, verify_submission_id

logger = logging.getLogger("uvicorn.error")


def run_auto_ai_verification(db: Session, submission: Submission) -> dict | None:
    """
    Compare form vs ID scan after submit.

    If confidence >= threshold (default 50%), mark confirmed automatically.
    Otherwise keep status submitted and store AI results for admin review.
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

    if confidence >= threshold:
        submission.status = SubmissionStatus.CONFIRMED.value
        submission.confirmed_at = datetime.now(timezone.utc)
        submission.ai_auto_confirmed = True
        result["auto_confirmed"] = True
        logger.info(
            "Auto-confirmed submission %s (AI confidence %.0f%%)",
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
