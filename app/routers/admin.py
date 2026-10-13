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
from app.deps import OWNER_VIEW_COOKIE, admin_can_sign_in, get_current_admin, get_superadmin
from app.models import (
    ACTIVE_SUBMISSION_STATUSES,
    AdminUser,
    Apartment,
    Document,
    FormLink,
    HostSection,
    Submission,
    SubmissionStatus,
)
from pydantic import ValidationError

from app.schemas import AdminLogin, AdminSubmissionEdit
from app.services.admin_context import (
    build_export_url,
    filters_active,
    get_admin_counts,
    query_ai_auto_confirmed,
    query_submissions,
)
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.property_placeholder import is_placeholder
from app.services.public_urls import (
    admin_login_url,
    admin_share_url,
    guest_register_url,
    shared_guest_form_url,
)
from app.services.registration import get_or_create_shared_link
from app.services.admin_users import admin_accounts_from_settings
from app.services.demo_data import has_demo_data, remove_demo_data
from app.services.platform_stats import build_platform_stats
from app.services.apartment_links import ensure_unique_slug, slugify_name
from app.services.sections import (
    MAX_ADMINS_PER_SECTION,
    MIN_PASSWORD_LENGTH,
    add_section_admin,
    section_admins,
    section_apartments,
    section_stats,
    unique_section_slug,
    validate_new_admin,
)
from app.services.sanitize import clean_text
from app.services.id_preview import get_preview_image
from app.services.rate_limit import client_ip, login_failures
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
from app.services.qrcode_gen import make_qr_png
from app.services.submissions import (
    archive_submission,
    assign_apartment,
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
    keys = (f"ip:{client_ip(request)}", f"user:{username.lower()}")
    if any(login_failures.is_limited(k) for k in keys):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Too many failed attempts. Try again in 15 minutes."},
            status_code=429,
        )
    admin = db.query(AdminUser).filter(AdminUser.username == username).first()
    if not admin or not verify_password(password, admin.password_hash):
        for k in keys:
            login_failures.hit(k)
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=401,
        )
    if not admin.is_active:
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "This account is blocked. Contact the platform owner."},
            status_code=403,
        )
    if not admin_can_sign_in(admin):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "This host account is switched off. Contact the admin."},
            status_code=403,
        )
    for k in keys:
        login_failures.reset(k)
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(admin.username)
    redirect = RedirectResponse(url="/admin/", status_code=303)
    redirect.delete_cookie(OWNER_VIEW_COOKIE)
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
    redirect.delete_cookie(OWNER_VIEW_COOKIE)
    return redirect


def _get_sub(db: Session, admin: AdminUser, public_id: str) -> Submission | None:
    """Submission by public id, only if it belongs to the admin's section."""
    return (
        db.query(Submission)
        .options(joinedload(Submission.document), joinedload(Submission.apartment))
        .filter(Submission.public_id == public_id, Submission.section_id == admin.active_section_id)
        .first()
    )


def _counts_context(db: Session, admin: AdminUser) -> dict:
    ctx = get_admin_counts(db, admin.active_section_id)
    ctx["ai_threshold_pct"] = int(settings.ai_auto_confirm_threshold * 100)
    ctx["section"] = admin.active_section
    ctx["apartment_count"] = len(section_apartments(db, admin.active_section_id, active_only=True))
    return ctx


def _section_guest_url(admin: AdminUser) -> str:
    """Each host's own guest link: /register/<host>. (The old /register still opens the default host.)"""
    section = admin.active_section
    if section is None:
        return guest_register_url()
    return guest_register_url(section.slug)


def _ai_setup_hint() -> str:
    p = settings.ai_provider_normalized
    if p == "local":
        return "Unlimited free OCR on your server"
    if p == "gemini":
        return "Free API key: aistudio.google.com/apikey (daily limit)"
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
        {"request": request, "admin": admin, **_counts_context(db, admin)},
    )


@router.get("/ai-approved", response_class=HTMLResponse)
async def admin_ai_approved(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    submissions = query_ai_auto_confirmed(db, admin.active_section_id)
    rows = []
    for sub in submissions:
        ai = load_verification_result(sub)
        confidence_pct = None
        if ai and ai.get("confidence") is not None:
            confidence_pct = int(float(ai["confidence"]) * 100)
        rows.append({"submission": sub, "confidence_pct": confidence_pct, "ai_summary": (ai or {}).get("summary")})
    return templates.TemplateResponse(
        "admin/ai_approved.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "rows": rows,
            "ai_threshold_pct": int(settings.ai_auto_confirm_threshold * 100),
        },
    )


@router.get("/share", response_class=HTMLResponse)
async def admin_share(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    get_or_create_shared_link(db, admin.active_section_id)
    return templates.TemplateResponse(
        "admin/share.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "guest_link": _section_guest_url(admin),
            "guest_link_direct": shared_guest_form_url(db, admin.active_section_id),
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
    ai_filter: str | None = Query(default=None),
    arrival_from: str | None = Query(default=None),
    arrival_to: str | None = Query(default=None),
    submitted_from: str | None = Query(default=None),
    submitted_to: str | None = Query(default=None),
):
    try:
        submissions = query_submissions(
            db,
            admin.active_section_id,
            q=q,
            status_filter=status_filter,
            ai_filter=ai_filter,
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
            **_counts_context(db, admin),
            "submissions": submissions,
            "export_url": export_url,
            "q": q or "",
            "status_filter": status_filter or "",
            "ai_filter": ai_filter or "",
            "arrival_from": (arrival_from or "").strip()[:10],
            "arrival_to": (arrival_to or "").strip()[:10],
            "submitted_from": (submitted_from or "").strip()[:10],
            "submitted_to": (submitted_to or "").strip()[:10],
            "statuses": [s.value for s in SubmissionStatus if s != SubmissionStatus.ARCHIVED],
            "result_count": len(submissions),
            "filters_active": filters_active(
                q=q,
                status_filter=status_filter,
                ai_filter=ai_filter,
                arrival_from=arrival_from,
                arrival_to=arrival_to,
                submitted_from=submitted_from,
                submitted_to=submitted_to,
            ),
        },
    )


# ---------------- Apartments (per section) ----------------


def _get_apartment(db: Session, admin: AdminUser, apt_public_id: str) -> Apartment:
    apt = (
        db.query(Apartment)
        .filter(Apartment.public_id == apt_public_id, Apartment.section_id == admin.active_section_id)
        .first()
    )
    if not apt:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return apt


def _apartment_fields(form) -> tuple[str, str, int | None, str | None]:
    name = clean_text(str(form.get("name", "")), 128)
    address = clean_text(str(form.get("address", "")), 500)
    raw_rate = str(form.get("nightly_rate", "")).strip().replace(" ", "")
    rate = None
    if raw_rate:
        if not raw_rate.isdigit() or not 0 < int(raw_rate) <= 1_000_000:
            return name, address, None, "Nightly rate must be a whole number of dirhams (MAD)."
        rate = int(raw_rate)
    if not name:
        return name, address, rate, "Give the apartment a name."
    if not address:
        return name, address, rate, "Add the apartment's full address (it is printed on the fiche de police)."
    return name, address, rate, None


@router.get("/apartments", response_class=HTMLResponse)
async def apartments_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    apartments = section_apartments(db, admin.active_section_id)
    guest_counts = dict(
        db.query(Submission.apartment_id, func.count(Submission.id))
        .filter(Submission.section_id == admin.active_section_id)
        .group_by(Submission.apartment_id)
        .all()
    )
    return templates.TemplateResponse(
        "admin/apartments.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "apartments": apartments,
            "guest_counts": guest_counts,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/apartments")
async def apartment_create(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    name, address, rate, err = _apartment_fields(await request.form())
    if err:
        return RedirectResponse(url=f"/admin/apartments?error={quote(err)}#add", status_code=303)
    apt = Apartment(
        section_id=admin.active_section_id, name=name, address=address, nightly_rate=rate, is_active=True
    )
    apt.slug = ensure_unique_slug(db, slugify_name(f"{admin.active_section.slug}-{name}"))
    db.add(apt)
    db.commit()
    return RedirectResponse(url=f"/admin/apartments?msg={quote(f'{name} added.')}", status_code=303)


@router.post("/apartments/{apt_public_id}/edit")
async def apartment_edit(
    apt_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    apt = _get_apartment(db, admin, apt_public_id)
    name, address, rate, err = _apartment_fields(await request.form())
    if err:
        return RedirectResponse(url=f"/admin/apartments?error={quote(err)}", status_code=303)
    apt.name, apt.address, apt.nightly_rate = name, address, rate
    db.commit()
    return RedirectResponse(
        url=f"/admin/apartments?msg={quote(f'{name} saved. New PDFs will use the updated details.')}",
        status_code=303,
    )


@router.post("/apartments/{apt_public_id}/delete")
async def apartment_delete(
    apt_public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    apt = _get_apartment(db, admin, apt_public_id)
    used = db.query(func.count(Submission.id)).filter(Submission.apartment_id == apt.id).scalar() or 0
    if used:
        # Guests' records and PDFs still point to it: hide it instead of deleting.
        apt.is_active = False
        db.commit()
        msg = f"{apt.name} is hidden from the list. It stays on the {used} guest record(s) that use it."
    else:
        msg = f"{apt.name} deleted."
        db.delete(apt)
        db.commit()
    return RedirectResponse(url=f"/admin/apartments?msg={quote(msg)}", status_code=303)


@router.post("/apartments/{apt_public_id}/restore")
async def apartment_restore(
    apt_public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    apt = _get_apartment(db, admin, apt_public_id)
    apt.is_active = True
    db.commit()
    return RedirectResponse(url=f"/admin/apartments?msg={quote(f'{apt.name} is back in the list.')}", status_code=303)


# ---------------- Sections (platform owner only) ----------------


def _env_usernames() -> set[str]:
    return {u.lower() for u, _ in admin_accounts_from_settings()}


def _get_section(db: Session, section_public_id: str) -> HostSection:
    section = db.query(HostSection).filter(HostSection.public_id == section_public_id).first()
    if not section:
        raise HTTPException(status_code=404, detail="Host not found")
    return section


def _sections_redirect(msg: str = "", error: str = "", anchor: str = "", page: str = "sections") -> RedirectResponse:
    params = {k: v for k, v in (("msg", msg), ("error", error)) if v}
    base = "/admin/users" if page == "users" else "/admin/sections"
    url = base + (f"?{urlencode(params)}" if params else "") + (f"#{anchor}" if anchor else "")
    return RedirectResponse(url=url, status_code=303)


@router.get("/sections", response_class=HTMLResponse)
async def sections_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    sections = db.query(HostSection).order_by(HostSection.created_at, HostSection.id).all()
    rows = [
        {
            "section": sec,
            "admins": section_admins(db, sec.id),
            "stats": section_stats(db, sec.id),
            "guest_url": guest_register_url(sec.slug),
        }
        for sec in sections
    ]
    return templates.TemplateResponse(
        "admin/sections.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "rows": rows,
            "max_admins": MAX_ADMINS_PER_SECTION,
            "min_password": MIN_PASSWORD_LENGTH,
            "env_usernames": _env_usernames(),
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/sections")
async def section_create(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    form = await request.form()
    name = clean_text(str(form.get("name", "")), 128)
    if not name:
        return _sections_redirect(error="Give the host a name.", anchor="new")
    accounts = []
    for i in (1, 2):
        username = str(form.get(f"username{i}", "")).strip()
        password = str(form.get(f"password{i}", ""))
        if i == 2 and not username and not password:
            continue
        err = validate_new_admin(db, username, password)
        if not err and any(u.lower() == username.lower() for u, _ in accounts):
            err = "The two host users need different usernames."
        if err:
            return _sections_redirect(error=f"User {i}: {err}", anchor="new")
        accounts.append((username, password))

    section = HostSection(name=name, slug=unique_section_slug(db, name), is_active=True)
    db.add(section)
    db.flush()
    for username, password in accounts:
        add_section_admin(db, section, username, password)
    db.commit()
    get_or_create_shared_link(db, section.id)
    return _sections_redirect(msg=f"Host “{name}” created with {len(accounts)} user(s).", anchor=section.public_id)


@router.post("/sections/{section_public_id}/rename")
async def section_rename(
    section_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section = _get_section(db, section_public_id)
    name = clean_text(str((await request.form()).get("name", "")), 128)
    if not name:
        return _sections_redirect(error="Host name can't be empty.", anchor=section.public_id)
    section.name = name
    db.commit()
    return _sections_redirect(msg="Host renamed. Its guest link stays the same.", anchor=section.public_id)


@router.post("/sections/{section_public_id}/toggle")
async def section_toggle(
    section_public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section = _get_section(db, section_public_id)
    if section.id == admin.section_id:
        return _sections_redirect(error="You can't switch off your own section.", anchor=section.public_id)
    section.is_active = not section.is_active
    db.commit()
    state = "switched on" if section.is_active else "switched off: its users can't sign in and its guest link is closed"
    return _sections_redirect(msg=f"“{section.name}” {state}.", anchor=section.public_id)


@router.post("/sections/{section_public_id}/delete")
async def section_delete(
    section_public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section = _get_section(db, section_public_id)
    if section.id == admin.section_id:
        return _sections_redirect(error="You can't delete your own section.", anchor=section.public_id)
    guests = db.query(func.count(Submission.id)).filter(Submission.section_id == section.id).scalar() or 0
    if guests:
        return _sections_redirect(
            error=f"“{section.name}” has {guests} guest record(s). Switch it off instead, so nothing is lost.",
            anchor=section.public_id,
        )
    name = section.name
    db.query(AdminUser).filter(AdminUser.section_id == section.id).delete()
    db.query(Apartment).filter(Apartment.section_id == section.id).delete()
    db.query(FormLink).filter(FormLink.section_id == section.id).delete()
    db.delete(section)
    db.commit()
    return _sections_redirect(msg=f"Host “{name}” deleted.")


@router.post("/sections/{section_public_id}/admins")
async def section_add_admin(
    section_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section = _get_section(db, section_public_id)
    if len(section_admins(db, section.id)) >= MAX_ADMINS_PER_SECTION:
        return _sections_redirect(
            error=f"A host can have {MAX_ADMINS_PER_SECTION} users. Remove one first.", anchor=section.public_id
        )
    form = await request.form()
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))
    err = validate_new_admin(db, username, password)
    if err:
        return _sections_redirect(error=err, anchor=section.public_id)
    add_section_admin(db, section, username, password)
    db.commit()
    return _sections_redirect(msg=f"User “{username}” added to {section.name}.", anchor=section.public_id)


def _get_section_admin(db: Session, section: HostSection, admin_id: int) -> AdminUser:
    target = db.query(AdminUser).filter(AdminUser.id == admin_id, AdminUser.section_id == section.id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Admin not found")
    return target


@router.post("/sections/{section_public_id}/admins/{admin_id}/password")
async def section_admin_password(
    section_public_id: str,
    admin_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
    back: str = Query(default=""),
):
    section = _get_section(db, section_public_id)
    target = _get_section_admin(db, section, admin_id)
    if target.username.lower() in _env_usernames():
        return _sections_redirect(page=back, 
            error=f"“{target.username}” is set in the .env file. Change the password there.", anchor=section.public_id
        )
    password = str((await request.form()).get("password", ""))
    if len(password) < MIN_PASSWORD_LENGTH:
        return _sections_redirect(page=back, 
            error=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", anchor=section.public_id
        )
    target.password_hash = hash_password(password)
    db.commit()
    return _sections_redirect(page=back, msg=f"New password saved for “{target.username}”.", anchor=section.public_id)


@router.post("/sections/{section_public_id}/admins/{admin_id}/delete")
async def section_admin_delete(
    section_public_id: str,
    admin_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
    back: str = Query(default=""),
):
    section = _get_section(db, section_public_id)
    target = _get_section_admin(db, section, admin_id)
    if target.id == admin.id or target.is_superadmin:
        return _sections_redirect(page=back, error="You can't remove the admin account.", anchor=section.public_id)
    if target.username.lower() in _env_usernames():
        return _sections_redirect(page=back, 
            error=f"“{target.username}” is set in the .env file. Remove it there, then restart.", anchor=section.public_id
        )
    username = target.username
    db.delete(target)
    db.commit()
    return _sections_redirect(page=back, msg=f"User “{username}” removed. They are signed out.", anchor=section.public_id)


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
            **_counts_context(db, admin),
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
                **_counts_context(db, admin),
                "error": "Current password is incorrect.",
                "success": None,
            },
            status_code=400,
        )
    if len(new_pw) < MIN_PASSWORD_LENGTH:
        return templates.TemplateResponse(
            "admin/profile.html",
            {
                "request": request,
                "admin": admin,
                **_counts_context(db, admin),
                "error": f"New password must be at least {MIN_PASSWORD_LENGTH} characters.",
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
                **_counts_context(db, admin),
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
    sub = _get_sub(db, admin, public_id)
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
    needs_manual_review = (
        sub.status == SubmissionStatus.SUBMITTED.value
        and sub.ai_verification_at is not None
        and not sub.ai_auto_confirmed
    )
    return templates.TemplateResponse(
        "admin/submission_detail.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "submission": sub,
            "apartments": section_apartments(db, admin.active_section_id, active_only=True),
            "assigned_apartment": None if is_placeholder(sub.apartment) else sub.apartment,
            "flash": flash,
            "flash_error": flash_error,
            "id_retention_hours": settings.id_retention_hours_after_verify,
            "id_pending_verification": id_pending,
            "has_id_preview": has_id_file and id_file_exists,
            "ai_enabled": settings.ai_verification_enabled,
            "ai_provider_label": settings.ai_provider_label,
            "ai_setup_hint": _ai_setup_hint(),
            "ai_result": ai_result,
            "ai_auto_confirmed": sub.ai_auto_confirmed,
            "needs_manual_review": needs_manual_review,
            "ai_threshold_pct": int(settings.ai_auto_confirm_threshold * 100),
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
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status == SubmissionStatus.ARCHIVED.value:
        return RedirectResponse(url=f"/admin/submissions/{public_id}", status_code=303)
    return templates.TemplateResponse(
        "admin/submission_edit.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
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
    sub = _get_sub(db, admin, public_id)
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


def _apartment_from_form(db: Session, admin: AdminUser, raw) -> Apartment | None:
    """Active apartment of the admin's section chosen in a form, or None."""
    apt_public_id = str(raw or "").strip()
    if not apt_public_id:
        return None
    return (
        db.query(Apartment)
        .filter(
            Apartment.public_id == apt_public_id,
            Apartment.section_id == admin.active_section_id,
            Apartment.is_active.is_(True),
        )
        .first()
    )


@router.post("/submissions/{public_id}/confirm")
async def confirm_submission_route(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = _get_sub(db, admin, public_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.status != SubmissionStatus.SUBMITTED.value:
        return RedirectResponse(url=f"/admin/submissions/{public_id}", status_code=303)
    form = await request.form()
    apartment = _apartment_from_form(db, admin, form.get("apartment"))
    if not apartment:
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}?error={quote('Choose the apartment before confirming.')}#decision",
            status_code=303,
        )
    msg = confirm_submission(db, sub, apartment)
    return RedirectResponse(
        url=f"/admin/submissions/{public_id}?msg={quote(msg)}",
        status_code=303,
    )


@router.post("/submissions/{public_id}/apartment")
async def assign_apartment_route(
    public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = _get_sub(db, admin, public_id)
    if not sub or sub.status == SubmissionStatus.ARCHIVED.value:
        raise HTTPException(status_code=404, detail="Submission not found")
    form = await request.form()
    apartment = _apartment_from_form(db, admin, form.get("apartment"))
    if not apartment:
        return RedirectResponse(
            url=f"/admin/submissions/{public_id}?error={quote('Choose an apartment from the list.')}",
            status_code=303,
        )
    msg = assign_apartment(db, sub, apartment)
    return RedirectResponse(url=f"/admin/submissions/{public_id}?msg={quote(msg)}", status_code=303)


@router.post("/submissions/{public_id}/archive")
async def archive_submission_route(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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
        target = _section_guest_url(admin)
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
        admin.active_section_id,
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
        admin.active_section_id,
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
            **_counts_context(db, admin),
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
            "guest_register_url": _section_guest_url(admin),
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
        .filter(
            Submission.section_id == admin.active_section_id,
            Submission.status == SubmissionStatus.ARCHIVED.value,
        )
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
    purge_ok, purge_msg = can_quarterly_purge(db, admin.active_section_id)
    counts = _counts_context(db, admin)
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
    data = build_archive_zip(db, admin.active_section_id)
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
    purge_ok, purge_msg = can_quarterly_purge(db, admin.active_section_id)
    if not purge_ok:
        return RedirectResponse(
            url=f"/admin/archive?error={quote(purge_msg)}",
            status_code=303,
        )
    current = len(archived_submissions(db, admin.active_section_id))
    if current == 0:
        return RedirectResponse(
            url="/admin/archive?error=No+archived+records+to+purge",
            status_code=303,
        )
    purged, cumulative = purge_all_archived(db, admin.active_section_id)
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
    sub = _get_sub(db, admin, public_id)
    if not sub or sub.status != SubmissionStatus.ARCHIVED.value:
        raise HTTPException(status_code=404, detail="Archived submission not found")
    permanently_delete_submission(db, sub)
    return RedirectResponse(url="/admin/archive?purged=1", status_code=303)


@router.get("/submissions/{public_id}/pdf")
async def download_fiche_pdf(
    public_id: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    sub = _get_sub(db, admin, public_id)
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
    sub = _get_sub(db, admin, public_id)
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


# ---------------- Platform owner: view any section, block admins, statistics ----------------


@router.post("/sections/{section_public_id}/open")
async def section_open(
    section_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section = _get_section(db, section_public_id)
    target = str((await request.form()).get("next", "")).strip()
    if not target.startswith("/admin/") or target.startswith("//"):
        target = "/admin/"
    redirect = RedirectResponse(url=target, status_code=303)
    if section.id == admin.section_id:
        redirect.delete_cookie(OWNER_VIEW_COOKIE)
    else:
        redirect.set_cookie(
            OWNER_VIEW_COOKIE,
            section.public_id,
            httponly=True,
            secure=settings.force_https,
            samesite="lax",
            max_age=settings.session_max_age_hours * 3600,
        )
    return redirect


@router.post("/view/exit")
async def section_view_exit(admin: AdminUser = Depends(get_superadmin)):
    redirect = RedirectResponse(url="/admin/stats", status_code=303)
    redirect.delete_cookie(OWNER_VIEW_COOKIE)
    return redirect


@router.get("/guests", response_class=HTMLResponse)
async def all_guests_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
    q: str | None = Query(default=None),
    host: str | None = Query(default=None),
    status_filter: str | None = Query(default=None),
):
    """Every guest registration across all hosts (admin only)."""
    sections = db.query(HostSection).order_by(HostSection.name).all()
    query = (
        db.query(Submission)
        .options(joinedload(Submission.apartment), joinedload(Submission.document))
        .order_by(Submission.submitted_at.desc())
    )
    section_by_pid = {sec.public_id: sec for sec in sections}
    if host and host in section_by_pid:
        query = query.filter(Submission.section_id == section_by_pid[host].id)
    allowed = {st.value for st in SubmissionStatus}
    if status_filter in allowed:
        query = query.filter(Submission.status == status_filter)
    if q and q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Submission.last_name.ilike(term),
                Submission.first_name.ilike(term),
                Submission.id_document_number.ilike(term),
                Submission.nationality.ilike(term),
            )
        )
    total = query.count()
    guests = query.limit(300).all()
    section_by_id = {sec.id: sec for sec in sections}
    return templates.TemplateResponse(
        "admin/guests.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "guests": guests,
            "total": total,
            "sections": sections,
            "section_by_id": section_by_id,
            "q": q or "",
            "host": host or "",
            "status_filter": status_filter or "",
            "statuses": [st.value for st in SubmissionStatus if st != SubmissionStatus.CANCELLED],
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def all_users_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    """Every host user profile (admin only)."""
    users = (
        db.query(AdminUser)
        .options(joinedload(AdminUser.section))
        .order_by(AdminUser.is_superadmin.desc(), AdminUser.username)
        .all()
    )
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "users": users,
            "env_usernames": _env_usernames(),
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/sections/{section_public_id}/admins/{admin_id}/block")
async def section_admin_block(
    section_public_id: str,
    admin_id: int,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
    back: str = Query(default=""),
):
    section = _get_section(db, section_public_id)
    target = _get_section_admin(db, section, admin_id)
    if target.id == admin.id or target.is_superadmin:
        return _sections_redirect(page=back, error="You can't block the admin account.", anchor=section.public_id)
    if target.username.lower() in _env_usernames():
        return _sections_redirect(page=back, 
            error=f"“{target.username}” is set in the .env file and is unblocked on every restart. Remove it there instead.",
            anchor=section.public_id,
        )
    target.is_active = not target.is_active
    db.commit()
    msg = (
        f"“{target.username}” is unblocked and can sign in again."
        if target.is_active
        else f"“{target.username}” is blocked and signed out everywhere."
    )
    return _sections_redirect(page=back, msg=msg, anchor=section.public_id)


@router.get("/stats", response_class=HTMLResponse)
async def platform_stats_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    return templates.TemplateResponse(
        "admin/stats.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "stats": build_platform_stats(db),
            "has_demo": has_demo_data(db),
            "msg": request.query_params.get("msg"),
        },
    )


@router.post("/stats/demo/remove")
async def remove_demo(
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    sections, guests = remove_demo_data(db)
    redirect = RedirectResponse(
        url=f"/admin/stats?msg={quote(f'Demo data removed: {sections} host(s), {guests} guest record(s).')}",
        status_code=303,
    )
    redirect.delete_cookie(OWNER_VIEW_COOKIE)
    return redirect


api_router = APIRouter(prefix="/api/admin", tags=["admin-api"])


@api_router.post("/login")
def api_login(body: AdminLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    keys = (f"ip:{client_ip(request)}", f"user:{body.username.strip().lower()}")
    if any(login_failures.is_limited(k) for k in keys):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    admin = db.query(AdminUser).filter(AdminUser.username == body.username, AdminUser.is_active).first()
    if not admin or not verify_password(body.password, admin.password_hash):
        for k in keys:
            login_failures.hit(k)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not admin_can_sign_in(admin):
        raise HTTPException(status_code=403, detail="Host account is switched off")
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()
    for k in keys:
        login_failures.reset(k)
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
