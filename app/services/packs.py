"""Packs of guest registrations ("fiches"): catalogue, quota state, activation, orders.

Rules
- One fiche = one guest registration received through a host's link.
- A pack ends when its fiches are used up or when its validity period is over, whichever comes first.
  Nothing is deleted: the host keeps its dashboard, only new guest registrations are refused.
- Buying a new pack before the old one ended keeps the unused fiches (they are added to the new pack).
- A host pays by bank transfer; the admin confirms the order, which activates the pack immediately.
"""

import calendar
import math
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import HostPack, PackOrder

PACK_MONTHS = 2
TRIAL_KEY = "essai"
CUSTOM_KEY = "complement"
LOW_FICHES = 10          # warn when this few (or 10% of a big pack) are left
EXPIRY_WARNING_DAYS = 7

# key -> pack. max_properties None = no limit.
PACKS: dict[str, dict] = {
    "petite": {
        "name": "Petite activité", "audience": "Moins de 5 logements",
        "fiches": 100, "price": 50, "max_properties": 4, "icon": "home",
    },
    "moyenne": {
        "name": "Moyenne activité", "audience": "De 5 à 10 logements",
        "fiches": 250, "price": 110, "max_properties": 10, "icon": "building",
    },
    "grande": {
        "name": "Grande activité", "audience": "Plus de 10 logements",
        "fiches": 600, "price": 240, "max_properties": None, "icon": "building",
    },
    "petit_hotel": {
        "name": "Petit hôtel", "audience": "Jusqu'à environ 30 chambres",
        "fiches": 1500, "price": 525, "max_properties": None, "icon": "building",
    },
    "grand_hotel": {
        "name": "Grand hôtel", "audience": "Plus de 30 chambres",
        "fiches": 4000, "price": 1200, "max_properties": None, "icon": "building",
    },
}
# Not for sale: given automatically to a new host, or by the admin.
TRIAL = {"name": "Essai gratuit", "fiches": 10, "days": 14, "max_properties": 4}
CUSTOM = {"name": "Complément de fiches", "max_properties": None}
TOPUP = {"name": "Recharge de fiches", "fiches": 50, "price": 30}

PACK_NAMES = {**{k: v["name"] for k, v in PACKS.items()}, TRIAL_KEY: TRIAL["name"], CUSTOM_KEY: CUSTOM["name"]}

ORDER_STATUS_LABELS = {
    "awaiting_payment": "En attente de paiement",
    "receipt_sent": "Reçu envoyé, en vérification",
    "confirmed": "Confirmée",
    "refused": "Refusée",
    "cancelled": "Annulée",
}
PENDING_STATUSES = ("awaiting_payment", "receipt_sent")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year, month = dt.year + month_index // 12, month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def max_properties_for(pack_key: str) -> int | None:
    if pack_key in PACKS:
        return PACKS[pack_key]["max_properties"]
    if pack_key == TRIAL_KEY:
        return TRIAL["max_properties"]
    return None


@dataclass
class PackState:
    pack: HostPack | None
    status: str               # none | active | exhausted | expired
    name: str = ""
    total: int = 0
    used: int = 0
    remaining: int = 0
    percent: int = 0          # share used, 0-100
    days_left: int = 0
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    carried_over: int = 0
    low: bool = False
    expiring_soon: bool = False
    max_properties: int | None = None

    @property
    def accepts(self) -> bool:
        return self.status == "active"


def pack_state(pack: HostPack | None, now: datetime | None = None) -> PackState:
    if pack is None:
        return PackState(pack=None, status="none")
    now = now or now_utc()
    expires, starts = aware(pack.expires_at), aware(pack.starts_at)
    total, used = pack.fiches_total, pack.fiches_used
    remaining = max(total - used, 0)
    if now > expires:
        status = "expired"
    elif remaining <= 0:
        status = "exhausted"
    else:
        status = "active"
    seconds_left = (expires - now).total_seconds()
    days_left = math.ceil(seconds_left / 86400) if seconds_left > 0 else 0
    return PackState(
        pack=pack, status=status, name=PACK_NAMES.get(pack.pack_key, pack.pack_key),
        total=total, used=used, remaining=remaining,
        percent=min(100, round(100 * used / total)) if total else 100,
        days_left=days_left, starts_at=starts, expires_at=expires, carried_over=pack.carried_over,
        low=status == "active" and remaining <= max(LOW_FICHES, round(total * 0.10)),
        expiring_soon=status == "active" and days_left <= EXPIRY_WARNING_DAYS,
        max_properties=max_properties_for(pack.pack_key),
    )


def current_pack(db: Session, section_id: int) -> HostPack | None:
    return (
        db.query(HostPack)
        .filter(HostPack.section_id == section_id, HostPack.status == "active")
        .order_by(HostPack.id.desc())
        .first()
    )


def host_state(db: Session, section_id: int) -> PackState:
    return pack_state(current_pack(db, section_id))


def can_accept_registration(db: Session, section_id: int) -> tuple[bool, PackState]:
    state = host_state(db, section_id)
    return state.accepts, state


def consume_fiche(db: Session, section_id: int) -> bool:
    """Count one received registration on the host's current pack (caller commits)."""
    pack = current_pack(db, section_id)
    if pack is None:
        return False
    pack.fiches_used += 1
    db.flush()
    return True


def property_limit(db: Session, section_id: int) -> tuple[int | None, str]:
    """Maximum number of properties allowed by the host's latest pack (and that pack's name)."""
    latest = db.query(HostPack).filter(HostPack.section_id == section_id).order_by(HostPack.id.desc()).first()
    if latest is None:
        return TRIAL["max_properties"], TRIAL["name"]
    return max_properties_for(latest.pack_key), PACK_NAMES.get(latest.pack_key, latest.pack_key)


# ---------------------------------------------------------------- activation


def activate_pack(db: Session, section_id: int, pack_key: str, *, source: str,
                  order: PackOrder | None = None, now: datetime | None = None) -> HostPack:
    """Make `pack_key` the host's current pack. Unused fiches of a still-valid pack are carried over."""
    now = now or now_utc()
    prev = current_pack(db, section_id)
    carried = 0
    if prev is not None:
        prev_state = pack_state(prev, now)
        if prev_state.status == "active":
            carried = prev_state.remaining
        prev.status = "replaced"

    if pack_key == TRIAL_KEY:
        fiches, expires = TRIAL["fiches"], now + timedelta(days=TRIAL["days"])
    elif pack_key in PACKS:
        fiches, expires = PACKS[pack_key]["fiches"], add_months(now, PACK_MONTHS)
    else:
        raise ValueError(f"Unknown pack: {pack_key}")

    pack = HostPack(
        section_id=section_id, pack_key=pack_key, fiches_total=fiches + carried, fiches_used=0,
        carried_over=carried, starts_at=now, expires_at=expires, status="active", source=source,
        order_id=order.id if order else None,
    )
    db.add(pack)
    db.flush()
    return pack


def add_fiches(db: Session, section_id: int, fiches: int, *, source: str,
               order: PackOrder | None = None, now: datetime | None = None) -> HostPack:
    """Add fiches to the current pack; if there is none or it has expired, start a 2-month one."""
    now = now or now_utc()
    pack = current_pack(db, section_id)
    if pack is not None and pack_state(pack, now).status != "expired":
        pack.fiches_total += fiches
        db.flush()
        return pack
    if pack is not None:
        pack.status = "replaced"
    pack = HostPack(
        section_id=section_id, pack_key=CUSTOM_KEY, fiches_total=fiches, fiches_used=0, carried_over=0,
        starts_at=now, expires_at=add_months(now, PACK_MONTHS), status="active", source=source,
        order_id=order.id if order else None,
    )
    db.add(pack)
    db.flush()
    return pack


def grant_trial(db: Session, section_id: int) -> HostPack:
    return activate_pack(db, section_id, TRIAL_KEY, source="trial")


# ---------------------------------------------------------------- orders

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easy to read and type


def new_reference(db: Session) -> str:
    while True:
        ref = "CMD-" + "".join(secrets.choice(_REF_ALPHABET) for _ in range(6))
        if not db.query(PackOrder.id).filter(PackOrder.reference == ref).first():
            return ref


def order_title(order: PackOrder) -> str:
    if order.kind == "topup":
        return f"Recharge de {order.fiches} fiches"
    return f"Pack {PACK_NAMES.get(order.pack_key, order.pack_key)}"


def create_order(db: Session, section_id: int, ordered_by_id: int | None, kind: str, pack_key: str = "") -> PackOrder:
    if kind == "topup":
        fiches, price, key = TOPUP["fiches"], TOPUP["price"], "topup"
    else:
        if pack_key not in PACKS:
            raise ValueError("Pack inconnu")
        fiches, price, key = PACKS[pack_key]["fiches"], PACKS[pack_key]["price"], pack_key
    order = PackOrder(
        reference=new_reference(db), section_id=section_id, ordered_by_id=ordered_by_id,
        kind=kind, pack_key=key, fiches=fiches, price_dh=price, status="awaiting_payment",
    )
    db.add(order)
    db.flush()
    return order


def confirm_order(db: Session, order: PackOrder) -> HostPack:
    """Admin confirmed the transfer: activate the pack (or add the fiches) immediately."""
    if order.status not in PENDING_STATUSES:
        raise ValueError("Cette commande a déjà été traitée.")
    if order.kind == "topup":
        pack = add_fiches(db, order.section_id, order.fiches, source="order", order=order)
    else:
        pack = activate_pack(db, order.section_id, order.pack_key, source="order", order=order)
    order.status = "confirmed"
    order.decided_at = now_utc()
    db.flush()
    return pack


def refuse_order(db: Session, order: PackOrder, reason: str) -> None:
    if order.status not in PENDING_STATUSES:
        raise ValueError("Cette commande a déjà été traitée.")
    order.status = "refused"
    order.refusal_reason = reason
    order.decided_at = now_utc()
    db.flush()


def cancel_order(db: Session, order: PackOrder) -> None:
    if order.status not in PENDING_STATUSES:
        raise ValueError("Cette commande ne peut plus être annulée.")
    order.status = "cancelled"
    order.decided_at = now_utc()
    db.flush()


def pending_orders_count(db: Session, section_id: int | None = None) -> int:
    q = db.query(PackOrder.id).filter(PackOrder.status.in_(PENDING_STATUSES))
    if section_id is not None:
        q = q.filter(PackOrder.section_id == section_id)
    return q.count()
