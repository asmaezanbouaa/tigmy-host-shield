"""Packs, orders (bank transfer + receipt) and the admin's tools to confirm them or grant packs."""

from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_admin, get_superadmin
from app.models import AdminUser, Apartment, HostSection, PackOrder
from app.routers.admin import _counts_context, _get_section
from app.services import packs as packs_service
from app.services.packs import (
    ORDER_STATUS_LABELS,
    PACKS,
    PENDING_STATUSES,
    TOPUP,
    host_state,
    order_title,
)
from app.services.sanitize import clean_text
from app.services.storage import absolute_path, ensure_storage_dirs, unlink_if_exists
from app.templating import templates

router = APIRouter(prefix="/admin", tags=["billing"])
settings = get_settings()

MAX_RECEIPT_BYTES = 5 * 1024 * 1024
RECEIPT_TYPES = {
    b"\xff\xd8": (".jpg", "image/jpeg"),
    b"\x89P": (".png", "image/png"),
    b"%P": (".pdf", "application/pdf"),
}


def bank_details() -> list[tuple[str, str]]:
    """Transfer details to show to hosts (empty when not configured in .env)."""
    rows = [
        ("Titulaire du compte", settings.bank_holder),
        ("Banque", settings.bank_name),
        ("Agence", settings.bank_branch),
        ("RIB", settings.bank_rib),
        ("IBAN", settings.bank_iban),
        ("Code SWIFT", settings.bank_swift),
    ]
    return [(label, value.strip()) for label, value in rows if value.strip()]


def _get_order(db: Session, admin: AdminUser, reference: str) -> PackOrder:
    order = (
        db.query(PackOrder)
        .options(joinedload(PackOrder.section), joinedload(PackOrder.ordered_by))
        .filter(PackOrder.reference == reference.upper())
        .first()
    )
    if not order or (not admin.is_superadmin and order.section_id != admin.active_section_id):
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return order


def _order_url(order: PackOrder, **params) -> str:
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in params.items() if v)
    return f"/admin/orders/{order.reference}" + (f"?{qs}" if qs else "")


# ---------------------------------------------------------------- host: packs page


@router.get("/packs", response_class=HTMLResponse)
async def packs_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    section_id = admin.active_section_id
    property_count = (
        db.query(func.count(Apartment.id))
        .filter(Apartment.section_id == section_id, Apartment.is_active.is_(True))
        .scalar()
        or 0
    )
    orders = (
        db.query(PackOrder)
        .filter(PackOrder.section_id == section_id)
        .order_by(PackOrder.id.desc())
        .limit(6)
        .all()
    )
    return templates.TemplateResponse(
        "admin/packs.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "property_count": property_count,
            "orders": orders,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/packs/order")
async def packs_order(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    section_id = admin.active_section_id
    form = await request.form()
    kind = "topup" if str(form.get("kind", "")) == "topup" else "pack"
    pack_key = str(form.get("pack_key", ""))
    state = host_state(db, section_id)

    if kind == "pack":
        if pack_key not in PACKS:
            return RedirectResponse("/admin/packs?error=" + quote("Pack inconnu."), status_code=303)
        limit = PACKS[pack_key]["max_properties"]
        count = (
            db.query(func.count(Apartment.id))
            .filter(Apartment.section_id == section_id, Apartment.is_active.is_(True))
            .scalar()
            or 0
        )
        if limit is not None and count > limit:
            return RedirectResponse(
                "/admin/packs?error=" + quote(f"Vous avez {count} logements : ce pack en autorise {limit} au maximum."),
                status_code=303,
            )
    elif state.status in ("none", "expired"):
        return RedirectResponse(
            "/admin/packs?error=" + quote("Votre pack a expiré : commandez un nouveau pack plutôt qu'une recharge."),
            status_code=303,
        )

    key = "topup" if kind == "topup" else pack_key
    existing = (
        db.query(PackOrder)
        .filter(PackOrder.section_id == section_id, PackOrder.pack_key == key, PackOrder.status.in_(PENDING_STATUSES))
        .first()
    )
    order = existing or packs_service.create_order(db, section_id, admin.id, kind, pack_key)
    db.commit()
    return RedirectResponse(_order_url(order, new="1" if not existing else ""), status_code=303)


# ---------------------------------------------------------------- orders (host and admin)


@router.get("/orders", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    status: str = Query(default="pending"),
):
    all_hosts = admin.is_superadmin and not admin.is_viewing_other_section
    query = db.query(PackOrder).options(joinedload(PackOrder.section), joinedload(PackOrder.ordered_by))
    if not all_hosts:
        query = query.filter(PackOrder.section_id == admin.active_section_id)
    if status == "pending":
        query = query.filter(PackOrder.status.in_(PENDING_STATUSES))
    elif status == "confirmed":
        query = query.filter(PackOrder.status == "confirmed")
    elif status == "closed":
        query = query.filter(PackOrder.status.in_(("refused", "cancelled")))
    else:
        status = "all"
    orders = query.order_by(PackOrder.id.desc()).limit(300).all()
    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "orders": orders,
            "status": status,
            "all_hosts": all_hosts,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/orders/{reference}", response_class=HTMLResponse)
async def order_detail(
    reference: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    order = _get_order(db, admin, reference)
    activates = None
    if order.kind == "pack" and order.status in PENDING_STATUSES:
        state = host_state(db, order.section_id)
        carried = state.remaining if state.status == "active" else 0
        activates = {"fiches": order.fiches, "carried": carried}
    return templates.TemplateResponse(
        "admin/order_detail.html",
        {
            "request": request,
            "admin": admin,
            **_counts_context(db, admin),
            "order": order,
            "title": order_title(order),
            "bank": bank_details(),
            "activates": activates,
            "receipt_is_pdf": bool(order.receipt_path and order.receipt_path.lower().endswith(".pdf")),
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
            "is_new": request.query_params.get("new") == "1",
        },
    )


@router.post("/orders/{reference}/receipt")
async def order_upload_receipt(
    reference: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
    receipt: UploadFile = File(...),
):
    order = _get_order(db, admin, reference)
    if order.status not in PENDING_STATUSES:
        return RedirectResponse(_order_url(order, error="Cette commande est déjà clôturée."), status_code=303)
    data = await receipt.read()
    if not data:
        return RedirectResponse(_order_url(order, error="Choisissez d'abord un fichier."), status_code=303)
    if len(data) > MAX_RECEIPT_BYTES:
        return RedirectResponse(_order_url(order, error="Fichier trop volumineux (5 Mo maximum)."), status_code=303)
    kind = next((v for magic, v in RECEIPT_TYPES.items() if data.startswith(magic)), None)
    if not kind:
        return RedirectResponse(
            _order_url(order, error="Envoyez une photo (JPG, PNG) ou un PDF du reçu de virement."), status_code=303
        )
    ensure_storage_dirs()
    path = settings.receipts_path / f"{order.reference}_{uuid4().hex[:8]}{kind[0]}"
    path.write_bytes(data)
    unlink_if_exists(order.receipt_path)
    order.receipt_path = str(path.relative_to(settings.storage_path.parent))
    order.receipt_uploaded_at = packs_service.now_utc()
    order.status = "receipt_sent"
    db.commit()
    return RedirectResponse(
        _order_url(order, msg="Reçu envoyé. Nous vérifions votre virement et activons votre pack dès réception."),
        status_code=303,
    )


@router.get("/orders/{reference}/receipt")
async def order_receipt_file(
    reference: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    order = _get_order(db, admin, reference)
    if not order.receipt_path:
        raise HTTPException(status_code=404, detail="Aucun reçu")
    path = absolute_path(order.receipt_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Reçu introuvable")
    media = {".pdf": "application/pdf", ".png": "image/png"}.get(path.suffix.lower(), "image/jpeg")
    return FileResponse(path, media_type=media)


@router.post("/orders/{reference}/cancel")
async def order_cancel(
    reference: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_current_admin),
):
    order = _get_order(db, admin, reference)
    try:
        packs_service.cancel_order(db, order)
    except ValueError as exc:
        return RedirectResponse(_order_url(order, error=str(exc)), status_code=303)
    db.commit()
    return RedirectResponse("/admin/packs?msg=" + quote(f"Commande {order.reference} annulée."), status_code=303)


@router.post("/orders/{reference}/confirm")
async def order_confirm(
    reference: str,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    order = _get_order(db, admin, reference)
    try:
        pack = packs_service.confirm_order(db, order)
    except ValueError as exc:
        return RedirectResponse(_order_url(order, error=str(exc)), status_code=303)
    db.commit()
    detail = (
        f"{order.fiches} fiches ajoutées" if order.kind == "topup"
        else f"pack {order_title(order)[5:]} activé ({pack.fiches_total} fiches"
        + (f", dont {pack.carried_over} reportées" if pack.carried_over else "") + ")"
    )
    return RedirectResponse(
        "/admin/orders?status=pending&msg=" + quote(f"Commande {order.reference} confirmée : {detail} pour {order.section.name}."),
        status_code=303,
    )


@router.post("/orders/{reference}/refuse")
async def order_refuse(
    reference: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    order = _get_order(db, admin, reference)
    reason = clean_text(str((await request.form()).get("reason", "")), 300)
    if not reason:
        return RedirectResponse(_order_url(order, error="Indiquez le motif du refus."), status_code=303)
    try:
        packs_service.refuse_order(db, order, reason)
    except ValueError as exc:
        return RedirectResponse(_order_url(order, error=str(exc)), status_code=303)
    db.commit()
    return RedirectResponse(
        "/admin/orders?status=pending&msg=" + quote(f"Commande {order.reference} refusée."), status_code=303
    )


# ---------------------------------------------------------------- admin: grant packs / fiches


def _hosts_redirect(msg: str = "", error: str = "", anchor: str = "") -> RedirectResponse:
    params = "&".join(f"{k}={quote(v)}" for k, v in (("msg", msg), ("error", error)) if v)
    return RedirectResponse("/admin/sections" + (f"?{params}" if params else "") + (f"#{anchor}" if anchor else ""), status_code=303)


@router.post("/sections/{section_public_id}/pack/grant")
async def grant_pack(
    section_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section: HostSection = _get_section(db, section_public_id)
    pack_key = str((await request.form()).get("pack_key", ""))
    if pack_key not in PACKS:
        return _hosts_redirect(error="Choisissez un pack.", anchor=section.public_id)
    pack = packs_service.activate_pack(db, section.id, pack_key, source="admin")
    db.commit()
    carried = f", dont {pack.carried_over} fiches reportées" if pack.carried_over else ""
    return _hosts_redirect(
        msg=f"Pack {PACKS[pack_key]['name']} offert à {section.name} ({pack.fiches_total} fiches{carried}).",
        anchor=section.public_id,
    )


@router.post("/sections/{section_public_id}/fiches/add")
async def add_fiches(
    section_public_id: str,
    request: Request,
    db: Session = Depends(get_db),
    admin: AdminUser = Depends(get_superadmin),
):
    section: HostSection = _get_section(db, section_public_id)
    raw = str((await request.form()).get("fiches", "")).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 10000:
        return _hosts_redirect(error="Indiquez un nombre de fiches entre 1 et 10 000.", anchor=section.public_id)
    packs_service.add_fiches(db, section.id, int(raw), source="admin")
    db.commit()
    return _hosts_redirect(msg=f"{int(raw)} fiches ajoutées à {section.name}.", anchor=section.public_id)
