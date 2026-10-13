import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import FormLink, FormLinkStatus, HostSection, Submission, SubmissionStatus
from app.services.date_validation import date_limits_for_form, parse_iso_date, validate_date_of_birth, validate_stay_dates
from app.services.property_placeholder import get_or_create_placeholder_apartment
from app.services.form_links import is_link_usable
from app.services.registration import get_or_create_shared_link
from app.services.sections import section_by_slug
from app.services.id_quality import check_id_image
from app.services.rate_limit import client_ip, guest_submissions, id_photo_checks
from app.services.sanitize import clean_text
from app.services.storage import ensure_storage_dirs, save_id_document, save_signature_from_data_url
from app.services.submission_pdfs import create_submission_pdfs
from app.services.auto_ai_verify import run_auto_ai_verification

from app.templating import templates

router = APIRouter(tags=["guest"])
settings = get_settings()

VALID_LANGS = frozenset({"fr", "en", "ar"})
ID_RETENTION_HOURS = settings.id_retention_hours_after_verify

class _GuestFormBody(BaseModel):
    last_name: str = Field(..., min_length=1, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=128)
    nationality: str = Field(..., min_length=1, max_length=128)
    date_of_birth: str = Field(..., min_length=8, max_length=16)
    country_of_residence: str = Field(..., min_length=1, max_length=128)
    number_of_guests: int = Field(..., ge=1, le=50)
    number_of_kids: int = Field(..., ge=0, le=30)
    arrival_date: str = Field(..., min_length=8, max_length=16)
    departure_date: str = Field(..., min_length=8, max_length=16)
    id_document_type: str = Field(..., min_length=1, max_length=64)
    id_document_number: str = Field(..., min_length=1, max_length=128)
    accept_internal_rules: bool
    accept_terms: bool
    signature_data_url: str = Field(..., min_length=100)

    @field_validator("date_of_birth", "arrival_date", "departure_date")
    @classmethod
    def parse_dates(cls, v: str) -> str:
        parse_iso_date(v)
        return v.strip()[:10]

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v: str) -> str:
        validate_date_of_birth(parse_iso_date(v))
        return v

    @field_validator("accept_internal_rules", "accept_terms", mode="before")
    @classmethod
    def must_be_true(cls, v):
        if v is not True and v != "true" and v != "on" and v != 1:
            raise ValueError("Rules and terms must be accepted")
        return True

    @field_validator("signature_data_url")
    @classmethod
    def validate_signature(cls, v: str) -> str:
        if not v.startswith("data:image/png;base64,"):
            raise ValueError("Invalid signature format")
        if len(v) < 200:
            raise ValueError("Signature is too short")
        return v

    @model_validator(mode="after")
    def check_dates_and_guests(self):
        validate_stay_dates(
            parse_iso_date(self.arrival_date),
            parse_iso_date(self.departure_date),
        )
        if self.number_of_kids > self.number_of_guests:
            raise ValueError("Number of children cannot exceed number of guests")
        return self


def _get_link_by_token(db: Session, token: str) -> FormLink:
    link = db.query(FormLink).filter(FormLink.token == token).first()
    if not link:
        raise HTTPException(status_code=404, detail="Form link not found")
    return link


def _link_usable(db: Session, link: FormLink) -> tuple[bool, str]:
    if link.section_id is not None:
        section = db.get(HostSection, link.section_id)
        if not section or not section.is_active:
            return False, "This registration link is no longer active."
    return is_link_usable(link)


def _form_context(request: Request, token: str, db: Session, link: FormLink):
    ok, message = _link_usable(db, link)

    fresh = request.query_params.get("fresh") == "1"
    lang_param = request.query_params.get("lang", "").strip().lower()
    if fresh:
        selected_lang = None
    else:
        selected_lang = lang_param if lang_param in VALID_LANGS else None

    host = db.get(HostSection, link.section_id) if link.section_id else None
    return {
        "request": request,
        "token": token,
        "host_name": host.name if host else "",
        "usable": ok,
        "error_message": message if not ok else "",
        "selected_lang": selected_lang,
        "fresh_start": fresh,
        "rules_fr": settings.load_rules_fr(),
        "rules_en": settings.load_rules_en(),
        "rules_ar": settings.load_rules_ar(),
        "date_limits": date_limits_for_form(),
        "id_retention_hours": ID_RETENTION_HOURS,
    }


@router.get("/register", response_class=HTMLResponse)
async def guest_register_redirect(db: Session = Depends(get_db)):
    """Default section's guest link (kept for links and QR codes already shared)."""
    link = get_or_create_shared_link(db)
    return RedirectResponse(url=f"/f/{link.token}?fresh=1", status_code=302)


@router.get("/register/{section_slug}", response_class=HTMLResponse)
async def guest_register_section_redirect(section_slug: str, db: Session = Depends(get_db)):
    section = section_by_slug(db, section_slug)
    if not section:
        raise HTTPException(status_code=404, detail="Registration link not found")
    link = get_or_create_shared_link(db, section.id)
    return RedirectResponse(url=f"/f/{link.token}?fresh=1", status_code=302)


@router.get("/f/{token}", response_class=HTMLResponse)
async def guest_form_page(request: Request, token: str, db: Session = Depends(get_db)):
    link = _get_link_by_token(db, token)
    return templates.TemplateResponse("guest/form.html", _form_context(request, token, db, link))


@router.get("/f/{token}/success", response_class=HTMLResponse)
async def guest_success_page(request: Request, token: str, db: Session = Depends(get_db)):
    outcome = request.query_params.get("outcome", "").strip().lower()
    link = db.query(FormLink).filter(FormLink.token == token).first()
    host = db.get(HostSection, link.section_id) if link and link.section_id else None
    return templates.TemplateResponse(
        "guest/success.html",
        {
            "request": request,
            "token": token,
            "host_name": host.name if host else "",
            "id_retention_hours": ID_RETENTION_HOURS,
            "ai_outcome": outcome,
            "ai_enabled": settings.ai_verification_enabled and settings.ai_auto_verify_on_submit,
        },
    )


def _id_quality_error(result) -> HTTPException:
    size = {k: result.metrics[k] for k in ("width", "height") if k in result.metrics}
    return HTTPException(status_code=400, detail={"code": f"id_{result.code}", "message": result.message, **size})


@router.post("/api/form/{token}/check-id")
async def check_id_photo(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    id_scan: UploadFile = File(...),
):
    """Instant quality check while the guest is still on the ID step (same rules as on submit)."""
    ip_key = client_ip(request)
    if id_photo_checks.is_limited(ip_key):
        raise HTTPException(status_code=429, detail="Too many photo checks. Please try again later.")
    link = _get_link_by_token(db, token)
    ok, message = _link_usable(db, link)
    if not ok:
        raise HTTPException(status_code=400, detail=message)
    data = await id_scan.read()
    if not data or len(data) > 10 * 1024 * 1024:
        return {"ok": False, "code": "id_too_large" if data else "id_unreadable"}
    id_photo_checks.hit(ip_key)
    result = await asyncio.to_thread(check_id_image, data, id_scan.filename or "")
    size = {k: result.metrics[k] for k in ("width", "height") if k in result.metrics}
    return {"ok": result.ok, "code": "ok" if result.ok else f"id_{result.code}", "message": result.message, **size}


@router.post("/api/form/{token}/submit")
async def submit_guest_form(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    last_name: str = Form(...),
    first_name: str = Form(...),
    nationality: str = Form(...),
    date_of_birth: str = Form(...),
    country_of_residence: str = Form(...),
    number_of_guests: int = Form(...),
    number_of_kids: int = Form(...),
    arrival_date: str = Form(...),
    departure_date: str = Form(...),
    id_document_type: str = Form(...),
    id_document_number: str = Form(...),
    accept_internal_rules: str = Form(...),
    accept_terms: str = Form(...),
    signature_data_url: str = Form(...),
    id_scan: UploadFile = File(...),
):
    ip_key = client_ip(request)
    if guest_submissions.is_limited(ip_key):
        raise HTTPException(
            status_code=429,
            detail="Too many registrations from this connection. Please try again later.",
        )

    ensure_storage_dirs()
    link = _get_link_by_token(db, token)
    ok, message = _link_usable(db, link)
    if not ok:
        raise HTTPException(status_code=400, detail=message)

    placeholder_apt = get_or_create_placeholder_apartment(db)

    try:
        payload = _GuestFormBody(
            last_name=last_name,
            first_name=first_name,
            nationality=nationality,
            date_of_birth=date_of_birth,
            country_of_residence=country_of_residence,
            number_of_guests=number_of_guests,
            number_of_kids=number_of_kids,
            arrival_date=arrival_date,
            departure_date=departure_date,
            id_document_type=id_document_type,
            id_document_number=id_document_number,
            accept_internal_rules=accept_internal_rules in ("true", "on", "1", True),
            accept_terms=accept_terms in ("true", "on", "1", True),
            signature_data_url=signature_data_url,
        )
    except ValidationError as exc:
        msgs = [e.get("msg", str(e)) for e in exc.errors()]
        raise HTTPException(status_code=400, detail="; ".join(msgs)) from exc

    if not id_scan.filename:
        raise HTTPException(status_code=400, detail="ID document scan is required")

    id_bytes = await id_scan.read()
    if not id_bytes:
        raise HTTPException(status_code=400, detail="ID document file is empty")
    quality = await asyncio.to_thread(check_id_image, id_bytes, id_scan.filename or "")
    if not quality.ok:
        raise _id_quality_error(quality)

    submission = Submission(
        form_link_id=link.id,
        section_id=link.section_id,
        apartment_id=placeholder_apt.id,
        last_name=clean_text(payload.last_name, 128),
        first_name=clean_text(payload.first_name, 128),
        nationality=clean_text(payload.nationality, 128),
        date_of_birth=clean_text(payload.date_of_birth, 16),
        country_of_residence=clean_text(payload.country_of_residence, 128),
        number_of_guests=payload.number_of_guests,
        number_of_kids=payload.number_of_kids,
        arrival_date=clean_text(payload.arrival_date, 16),
        departure_date=clean_text(payload.departure_date, 16),
        id_document_type=clean_text(payload.id_document_type, 64),
        id_document_number=clean_text(payload.id_document_number, 128),
        accept_internal_rules=True,
        accept_terms=True,
        signature_path="",
        status=SubmissionStatus.SUBMITTED.value,
        ip_address=request.client.host if request.client else None,
        user_agent=clean_text(request.headers.get("user-agent", "")[:512], 512)
        if request.headers.get("user-agent")
        else None,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(submission)
    db.flush()

    try:
        sig_rel = save_signature_from_data_url(
            payload.signature_data_url, submission.public_id
        )
        id_rel = save_id_document(
            id_bytes, id_scan.filename or "id.jpg", submission.public_id
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    submission.signature_path = sig_rel
    submission.id_document_path = id_rel

    create_submission_pdfs(db, submission, sig_rel)

    ai_outcome = "skipped"
    ai_result = run_auto_ai_verification(db, submission)
    if ai_result:
        ai_outcome = "approved" if ai_result.get("auto_confirmed") else "review"

    if link.single_use and not link.is_shared:
        link.status = FormLinkStatus.SUBMITTED.value

    db.commit()
    guest_submissions.hit(ip_key)

    redirect_url = f"/f/{token}/success?outcome={ai_outcome}"

    return {
        "success": True,
        "submission_id": submission.public_id,
        "redirect_url": redirect_url,
        "ai_outcome": ai_outcome,
    }
