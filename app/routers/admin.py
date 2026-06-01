import asyncio
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_admin
from app.models import (
    ACTIVE_SUBMISSION_STATUSES,
    AdminUser,
    Document,
    Submission,
    SubmissionStatus,
)
from pydantic import ValidationError

from app.schemas import AdminLogin, AdminSubmissionEdit
from app.services.admin_context import (
    build_export_url,
    filters_active,
    get_admin_counts,
    query_submissions,
)
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.property_placeholder import PROPERTY_PLACEHOLDER
from app.services.public_urls import (
    admin_login_url,
    admin_share_url,
    guest_register_url,
    shared_guest_form_url,
)
from app.services.registration import get_or_create_shared_link
from app.services.sanitize import clean_text
from app.services.id_preview import get_preview_image
from app.services.storage import absolute_path
from app.services.calendar_data import (
    build_month_calendar,
    fetch_events_for_range,
    month_nav,
)
from app.services.export_data import build_submissions_csv
from app.services.archive_export import (
    archived_submissions,
    build_archive_zip,
    can_quarterly_purge,
)
from app.services.ai_verification import (
    load_verification_result,
    save_verification_result,
    verify_submission_id,
)
from app.services.id_documents import purge_expired_id_documents, verify_id_document
from app.services.qrcode_gen import guest_register_url, make_qr_png
from app.services.submissions import (
    archive_submission,
    confirm_submission,
    permanently_delete_submission,
    purge_all_archived,
    update_submission_from_admin,
)

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()
from app.templating import templates


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    admin = db.query(AdminUser).filter(AdminUser.username == username, AdminUser.is_active).first()
    if not admin or not verify_password(password, admin.password_hash):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    token = create_access_token(admin.username)
    redirect = RedirectResponse(url="/admin/", status_code=303)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.force_https,
        samesite="lax",
        max_age=settings.session_max_age_hours * 3600,
    )
    return redirect


@router.post("/logout")
async def logout():
    redirect = RedirectResponse(url="/admin/login", status_code=303)
    redirect.delete_cookie(settings.session_cookie_name)
    return redirect


def _counts_context(db: Session) -> dict:
    return get_admin_counts(db)


def _ai_setup_hint() -> str:
    p = settings.ai_provider_normalized
    if p == "local":
        return "Unlimited free OCR on your server"
    if p == "gemini":
        return "Free API key: aistudio.google.com/apikey (daily limit)"
    if p == "ollama":
        return "Unlimited free: ollama pull moondream"
    if p == "openai":
        return "Paid credits required on OpenAI"
    return ""


@router.get("/", response_class=HTMLResponse)
async def admin_overview(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    return templates.TemplateResponse(
        "admin/overview.html",
        {"request": request, "admin": admin, **_counts_context(db)},
    )


@router.get("/share", response_class=HTMLResponse)
async def admin_share(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    get_or_create_shared_link(db)
    return templates.TemplateResponse(
        "admin/share.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "guest_link": guest_register_url(),
            "guest_link_direct": shared_guest_form_url(db),
            "admin_login_url": admin_login_url(),
            "admin_share_url": admin_share_url(),
        },
    )


@router.get("/submissions", response_class=HTMLResponse)
async def admin_submissions(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None),
    arrival_from: str | None = Query(default=None),
    arrival_to: str | None = Query(default=None),
    submitted_from: str | None = Query(default=None),
    submitted_to: str | None = Query(default=None),
):
    try:
        submissions = query_submissions(
            db,
            q=q,
            status_filter=status_filter,
            arrival_from=arrival_from,
            arrival_to=arrival_to,
            submitted_from=submitted_from,
            submitted_to=submitted_to,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Database error loading submissions. Run: python scripts/migrate_v2.py — {exc}",
        ) from exc

    export_url = build_export_url(
        status_filter=status_filter,
        arrival_from=arrival_from,
        arrival_to=arrival_to,
        submitted_from=submitted_from,
        submitted_to=submitted_to,
    )

    return templates.TemplateResponse(
        "admin/submissions.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "submissions": submissions,
            "export_url": export_url,
            "q": q or "",
            "status_filter": status_filter or "",
            "arrival_from": (arrival_from or "").strip()[:10],
            "arrival_to": (arrival_to or "").strip()[:10],
            "submitted_from": (submitted_from or "").strip()[:10],
            "submitted_to": (submitted_to or "").strip()[:10],
            "statuses": [s.value for s in SubmissionStatus if s != SubmissionStatus.ARCHIVED],
            "result_count": len(submissions),
            "filters_active": filters_active(
                q=q,
                status_filter=status_filter,
                arrival_from=arrival_from,
                arrival_to=arrival_to,
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            ),
        },
    )


@router.get("/apartments")
@router.get("/apartments/{path:path}")
@router.post("/apartments")
@router.post("/apartments/{path:path}")
async def apartments_removed():
    return RedirectResponse(url="/admin/submissions", status_code=303)


@router.get("/profile", response_class=HTMLResponse)
async def admin_profile(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    db.refresh(admin)
    err = request.query_params.get("error")
    ok_param = request.query_params.get("success")
    ok = "Password updated successfully." if ok_param == "password" else ok_param
    return templates.TemplateResponse(
        "admin/profile.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "error": err,
            "success": ok,
        },
    )


@router.post("/profile/password")
async def admin_change_password(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    form = await request.form()
    current = str(form.get("current_password", ""))
    new_pw = str(form.get("new_password", ""))
    confirm = str(form.get("confirm_password", ""))

    if not verify_password(current, admin.password_hash):
        return templates.TemplateResponse(
            "admin/profile.html",
            {
                "request": request,
                "admin": admin,
                **_counts_context(db),
                "error": "Current password is incorrect.",
                "success": None,
            },
            status_code=400,
        )
    if len(new_pw) < 4:
        return templates.TemplateResponse(
            "admin/profile.html",
            {
                "request": request,
                "admin": admin,
                **_counts_context(db),
                "error": "New password must be at least 4 characters.",
                "success": None,
            },
            status_code=400,
        )
    if new_pw != confirm:
        return templates.TemplateResponse(
            "admin/profile.html",
            {
                "request": request,
                "admin": admin,
                **_counts_context(db),
                "error": "New passwords do not match.",
                "success": None,
            },
            status_code=400,
        )

    admin.password_hash = hash_password(new_pw)
    db.commit()
    return RedirectResponse(url="/admin/profile?success=password", status_code=303)


@router.get("/submissions/{public_id}", response_class=HTMLResponse)
async def submission_detail(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.public_id == public_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    purge_expired_id_documents(db)
    flash = request.query_params.get("msg", "")
    flash_error = request.query_params.get("error", "")
    id_pending = bool(sub.id_document_path and not sub.id_document_verified_at)
    ai_result = load_verification_result(sub)
    has_id_file = bool(sub.id_document_path)
    id_file_exists = False
    if has_id_file:
        id_file_exists = absolute_path(sub.id_document_path).exists()
    return templates.TemplateResponse(
        "admin/submission_detail.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "submission": sub,
            "property_placeholder": PROPERTY_PLACEHOLDER,
            "flash": flash,
            "flash_error": flash_error,
            "id_retention_hours": settings.id_retention_hours_after_verify,
            "id_pending_verification": id_pending,
            "has_id_preview": has_id_file and id_file_exists,
            "ai_enabled": settings.ai_verification_enabled,
            "ai_provider_label": settings.ai_provider_label,
            "ai_setup_hint": _ai_setup_hint(),
            "ai_result": ai_result,
            "can_edit": sub.status in (
                SubmissionStatus.SUBMITTED.value,
                SubmissionStatus.CONFIRMED.value,
                SubmissionStatus.ISSUE.value,
            ),
            "can_confirm": sub.status == SubmissionStatus.SUBMITTED.value,
            "can_archive": sub.status in (
                SubmissionStatus.SUBMITTED.value,
                SubmissionStatus.CONFIRMED.value,
                SubmissionStatus.ISSUE.value,
            ),
        },
    )


@router.post("/submissions/{public_id}/status")
async def update_submission_status(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    form = await request.form()
    new_status = str(form.get("status", "")).strip()
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    allowed = {s.value for s in SubmissionStatus}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    sub.status = new_status
    db.commit()
    return RedirectResponse(url=f"/admin/submissions/{public_id}", status_code=303)


@router.get("/submissions/{public_id}/signature")
async def view_signature(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub or not sub.signature_path:
        raise HTTPException(status_code=404, detail="Signature not found")
    path = absolute_path(sub.signature_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Signature file missing")
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path, media_type=media)


@router.get("/submissions/{public_id}/edit", response_class=HTMLResponse)
async def submission_edit_page(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .filter(Submission.public_id == public_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status == SubmissionStatus.ARCHIVED.value:
        return RedirectResponse(url=f"/admin/submissions/{public_id}", status_code=303)
    return templates.TemplateResponse(
        "admin/submission_edit.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "submission": sub,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/submissions/{public_id}/edit")
async def submission_edit_save(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.public_id == public_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status == SubmissionStatus.ARCHIVED.value:
        raise HTTPException(status_code=400, detail="Cannot edit archived submission")

    form = await request.form()
    try:
        payload = AdminSubmissionEdit(
            last_name=str(form.get("last_name", "")),
            first_name=str(form.get("first_name", "")),
            nationality=str(form.get("nationality", "")),
            date_of_birth=str(form.get("date_of_birth", "")),
            country_of_residence=str(form.get("country_of_residence", "")),
            number_of_guests=int(form.get("number_of_guests", 1)),
            number_of_kids=int(form.get("number_of_kids", 0)),
            arrival_date=str(form.get("arrival_date", "")),
            departure_date=str(form.get("departure_date", "")),
            id_document_type=str(form.get("id_document_type", "")),
            id_document_number=str(form.get("id_document_number", "")),
            admin_notes=str(form.get("admin_notes", "")) or None,
        )
    except ValidationError as exc:
        err = "; ".join(e.get("msg", str(e)) for e in exc.errors())
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}/edit?error={quote(err)}",
            status_code=303,
        )

    update_submission_from_admin(
        db,
        sub,
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
        admin_notes=payload.admin_notes,
    )
    return RedirectResponse(
        url=f"/admin/submissions/{public_id}?msg={quote('Changes saved. PDFs regenerated.')}",
        status_code=303,
    )


@router.post("/submissions/{public_id}/confirm")
async def confirm_submission_route(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    msg = confirm_submission(db, sub)
    return RedirectResponse(
        url=f"/admin/submissions/{public_id}?msg={quote(msg)}",
        status_code=303,
    )


@router.post("/submissions/{public_id}/archive")
async def archive_submission_route(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status == SubmissionStatus.ARCHIVED.value:
        return RedirectResponse(url="/admin/archive", status_code=303)
    msg = archive_submission(db, sub)
    return RedirectResponse(
        url=f"/admin/submissions?sub=archived&msg={quote(msg)}", status_code=303
    )


def _wants_json_response(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept


@router.post("/submissions/{public_id}/ai-verify")
async def ai_verify_submission(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")

    try:
        result = await asyncio.to_thread(verify_submission_id, sub)
        save_verification_result(sub, result)
        db.commit()
        overall = result.get("overall", "unclear")
        if _wants_json_response(request):
            return JSONResponse(
                {
                    "ok": True,
                    "overall": overall,
                    "message": f"AI check complete: {overall}",
                }
            )
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}?msg={quote(f'AI check complete: {overall}')}",
            status_code=303,
        )
    except ValueError as exc:
        msg = str(exc)
        if _wants_json_response(request):
            return JSONResponse({"ok": False, "error": msg}, status_code=400)
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}?error={quote(msg)}",
            status_code=303,
        )
    except Exception as exc:
        msg = f"AI check failed: {exc}"
        if _wants_json_response(request):
            return JSONResponse({"ok": False, "error": msg}, status_code=500)
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}?error={quote(msg)}",
            status_code=303,
        )


@router.post("/submissions/{public_id}/verify-id")
async def verify_id_route(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub or not sub.id_document_path:
        raise HTTPException(status_code=404, detail="ID document not found")
    verify_id_document(db, sub)
    hours = settings.id_retention_hours_after_verify
    return RedirectResponse(
        url=f"/admin/submissions/{public_id}?msg={quote(f'ID verified. File will be deleted in {hours} hours.')}",
        status_code=303,
    )


@router.get("/submissions/{public_id}/id-preview")
async def id_document_preview(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Inline image preview (converts PDF first page to PNG)."""
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub or not sub.id_document_path:
        raise HTTPException(status_code=404, detail="ID document not found")
    path = absolute_path(sub.id_document_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ID file missing")
    try:
        data, media = get_preview_image(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=data, media_type=media, headers={"Cache-Control": "private, max-age=300"})


@router.get("/submissions/{public_id}/id-document")
async def download_id_document(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    """Download original ID file."""
    sub = db.query(Submission).filter(Submission.public_id == public_id).first()
    if not sub or not sub.id_document_path:
        raise HTTPException(status_code=404, detail="ID document not found")
    path = absolute_path(sub.id_document_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="ID file missing")
    media = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
    if path.suffix.lower() == ".png":
        media = "image/png"
    return FileResponse(path, media_type=media, filename=path.name)


@router.get("/qr.png")
async def guest_link_qr(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    url: str | None = Query(default=None, max_length=512),
):
    """QR code PNG for guest registration (/register by default)."""
    if url and url.strip():
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    else:
        target = guest_register_url()
    png = make_qr_png(target)
    return Response(content=png, media_type="image/png")


@router.get("/export.csv")
async def export_submissions_csv(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    include_archived: bool = Query(default=False),
    status_filter: str | None = Query(default=None),
    arrival_from: str | None = Query(default=None),
    arrival_to: str | None = Query(default=None),
):
    data = build_submissions_csv(
        db,
        include_archived=include_archived,
        status_filter=status_filter,
        arrival_from=arrival_from,
        arrival_to=arrival_to,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"guest_registrations_{stamp}.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
    view: str = Query(default="month"),
    include_archived: bool = Query(default=False),
):
    today = datetime.now(timezone.utc).date()
    y = year if year and 2000 <= year <= 2100 else today.year
    m = month if month and 1 <= month <= 12 else today.month

    import calendar as cal_mod

    last_day = cal_mod.monthrange(y, m)[1]
    range_start = date(y, m, 1)
    range_end = date(y, m, last_day)

    events = fetch_events_for_range(
        db,
        range_start,
        range_end,
        include_archived=include_archived,
    )
    weeks, month_start, month_end = build_month_calendar(y, m, events)
    (prev_y, prev_m), (next_y, next_m) = month_nav(y, m)

    month_name = month_start.strftime("%B %Y")
    month_start_iso = month_start.isoformat()
    month_end_iso = month_end.isoformat()
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    list_events = sorted(events, key=lambda e: (e.arrival_date, e.guest_name))

    return templates.TemplateResponse(
        "admin/calendar.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db),
            "weeks": weeks,
            "weekdays": weekdays,
            "month_name": month_name,
            "year": y,
            "month": m,
            "prev_year": prev_y,
            "prev_month": prev_m,
            "next_year": next_y,
            "next_month": next_m,
            "list_events": list_events,
            "view": view if view in ("month", "list") else "month",
            "include_archived": include_archived,
            "event_count": len(events),
            "month_start_iso": month_start_iso,
            "month_end_iso": month_end_iso,
            "guest_register_url": guest_register_url(),
        },
    )


@router.get("/archive", response_class=HTMLResponse)
async def archive_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    q: str | None = None,
):
    query = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.status == SubmissionStatus.ARCHIVED.value)
        .order_by(Submission.archived_at.desc(), Submission.submitted_at.desc())
    )
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Submission.last_name.ilike(term),
                Submission.first_name.ilike(term),
                Submission.id_document_number.ilike(term),
            )
        )
    submissions = query.limit(200).all()
    purge_ok, purge_msg = can_quarterly_purge(db)
    counts = _counts_context(db)
    return templates.TemplateResponse(
        "admin/archive.html",
        {
            "request": request,
            "admin": admin,
            **counts,
            "submissions": submissions,
            "q": q or "",
            "purge_ok": purge_ok,
            "purge_msg": purge_msg,
            "purge_interval_days": settings.archive_purge_interval_days,
        },
    )


@router.get("/archive/download.zip")
async def download_archive_zip(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    data = build_archive_zip(db)
    if not data:
        raise HTTPException(status_code=404, detail="No archived submissions to export")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="archive_export_{stamp}.zip"'
        },
    )


@router.post("/archive/purge-quarterly")
async def purge_archive_quarterly(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    purge_ok, purge_msg = can_quarterly_purge(db)
    if not purge_ok:
        return RedirectResponse(
            url=f"/admin/archive?error={quote(purge_msg)}",
            status_code=303,
        )
    current = len(archived_submissions(db))
    if current == 0:
        return RedirectResponse(
            url="/admin/archive?error=No+archived+records+to+purge",
            status_code=303,
        )
    purged, cumulative = purge_all_archived(db)
    msg = (
        f"Quarterly purge complete: {purged} record(s) removed. "
        f"Total archived (all time): {cumulative}."
    )
    return RedirectResponse(url=f"/admin/archive?msg={quote(msg)}", status_code=303)


@router.post("/archive/{public_id}/purge")
async def purge_archived_submission(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(
            Submission.public_id == public_id,
            Submission.status == SubmissionStatus.ARCHIVED.value,
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Archived submission not found")
    permanently_delete_submission(db, sub)
    return RedirectResponse(url="/admin/archive?purged=1", status_code=303)


@router.get("/submissions/{public_id}/pdf")
async def download_fiche_pdf(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.public_id == public_id)
        .first()
    )
    if not sub or not sub.document:
        raise HTTPException(status_code=404, detail="PDF not found")
    path = absolute_path(sub.document.pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=sub.document.filename,
    )


@router.get("/submissions/{public_id}/pdf/rules")
async def download_rules_pdf(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = (
        db.query(Submission)
        .options(joinedload(Submission.document))
        .filter(Submission.public_id == public_id)
        .first()
    )
    if not sub or not sub.document or not sub.document.rules_pdf_path:
        raise HTTPException(status_code=404, detail="Rules PDF not found")
    path = absolute_path(sub.document.rules_pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rules PDF file missing on disk")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=sub.document.rules_filename or "reglement.pdf",
    )


api_router = APIRouter(prefix="/api/admin", tags=["admin-api"])


@api_router.post("/login")
def api_login(body: AdminLogin, response: Response, db: Session = Depends(get_db)):
    admin = db.query(AdminUser).filter(AdminUser.username == body.username, AdminUser.is_active).first()
    if not admin or not verify_password(body.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(admin.username)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.force_https,
        samesite="lax",
        max_age=settings.session_max_age_hours * 3600,
    )
    return {"ok": True, "username": admin.username}
