import logging
import traceback
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import admin, billing, guest
from app.services.storage import ensure_storage_dirs

logger = logging.getLogger("uvicorn.error")
settings = get_settings()

if settings.is_production:
    _problems = settings.production_problems()
    if _problems:
        raise RuntimeError(
            "Refusing to start in production (APP_ENV=production). Fix these settings:\n  - "
            + "\n  - ".join(_problems)
        )

app = FastAPI(
    title=settings.app_name,
    docs_url="/api/docs" if settings.debug and not settings.is_production else None,
    redoc_url=None,
)

class ProxyHTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """Redirect external HTTP only; never redirect Railway's /health probe."""

    async def dispatch(self, request, call_next):
        if settings.force_https and request.url.path != "/health":
            proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
            if proto == "http":
                return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)
        return await call_next(request)


if settings.force_https:
    app.add_middleware(ProxyHTTPSRedirectMiddleware)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(guest.router)
app.include_router(admin.router)
app.include_router(admin.api_router)
app.include_router(billing.router)


@app.on_event("startup")
def on_startup():
    ensure_storage_dirs()
    try:
        from app.services.pdf_assets import ensure_fiche_banner, ensure_rules_banner

        ensure_fiche_banner()
        ensure_rules_banner()
        logger.info("PDF header banners ready")
        from app.config import get_settings

        get_settings.cache_clear()
        s = get_settings()
        from app.templating import templates

        templates.env.globals["app_name"] = s.app_name
        logger.info(
            "AI provider: %s (%s) — restart server after changing AI_PROVIDER in .env",
            s.ai_provider_normalized,
            s.ai_provider_label,
        )
        if s.ai_provider_normalized == "local":
            from app.services.ai_local import tesseract_available

            if tesseract_available():
                logger.info("Tesseract OCR ready for local AI checks")
            else:
                logger.warning(
                    "Tesseract not found — install: sudo apt install tesseract-ocr tesseract-ocr-fra"
                )
    except Exception as exc:
        logger.warning("PDF header banner prep failed: %s", exc)
    Base.metadata.create_all(bind=engine)
    try:
        import sys

        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from scripts.migrate_v2 import run_migrations as migrate_v2
        from scripts.migrate_v3 import run_migrations as migrate_v3
        from scripts.migrate_v4 import run_migrations as migrate_v4
        from scripts.migrate_v5 import run_migrations as migrate_v5
        from scripts.migrate_v6 import run_migrations as migrate_v6
        from scripts.migrate_v7 import run_migrations as migrate_v7
        from scripts.migrate_v8 import run_migrations as migrate_v8
        from app.services.id_documents import purge_expired_id_documents
        from app.database import SessionLocal

        from scripts.migrate_v8 import add_columns as add_section_columns

        add_section_columns()
        from scripts.migrate_v9 import add_columns as add_v9_columns

        add_v9_columns()
        migrate_v2()
        migrate_v3()
        migrate_v4()
        migrate_v5()
        migrate_v6()
        migrate_v7()
        migrate_v8()
        from scripts.migrate_v10 import run_migrations as migrate_v10

        migrate_v10()
        with SessionLocal() as db:
            n = purge_expired_id_documents(db)
            if n:
                logger.info("Purged %s expired ID document(s)", n)
            from app.services.admin_users import ensure_admin_users
            from app.services.property_placeholder import get_or_create_placeholder_apartment
            from app.services.registration import get_or_create_shared_link

            admin_changes = ensure_admin_users(db)
            if admin_changes:
                logger.info("Admin users: %s", ", ".join(admin_changes))
            get_or_create_placeholder_apartment(db)
            get_or_create_shared_link(db)
    except Exception as exc:
        logger.warning("Database migration skipped or failed: %s", exc)


ERROR_TITLES = {
    401: "Connexion requise", 403: "Accès refusé", 404: "Page introuvable",
    405: "Action impossible", 429: "Trop de demandes", 500: "Une erreur est survenue",
}
ERROR_MESSAGES = {
    403: "Vous n'avez pas accès à cette page.",
    404: "Cette page n'existe pas ou a changé.",
    429: "Merci de réessayer un peu plus tard.",
    500: "Un problème est survenu de notre côté. Réessayez dans un instant.",
}


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "") and not request.url.path.startswith("/api/")


def _error_page(request: Request, status: int, message: str | None = None) -> HTMLResponse:
    from app.templating import templates

    is_admin = request.url.path.startswith("/admin")
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "status": status,
            "title": ERROR_TITLES.get(status, "Erreur"),
            "message": message or ERROR_MESSAGES.get(status, "Une erreur est survenue."),
            "back_url": "/admin/" if is_admin else None,
        },
        status_code=status,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception(request: Request, exc: StarletteHTTPException):
    headers = getattr(exc, "headers", None) or {}
    location = headers.get("Location") or headers.get("location")
    if location and exc.status_code in (301, 302, 303, 307, 308):
        return RedirectResponse(location, status_code=exc.status_code)
    if _wants_html(request):
        if exc.status_code == 401 and request.url.path.startswith("/admin"):
            return RedirectResponse("/admin/login", status_code=303)  # session ended: back to the sign-in page
        message = exc.detail if isinstance(exc.detail, str) else None
        return _error_page(request, exc.status_code, message)
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers or None)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s", request.method, request.url.path)
    logger.error(traceback.format_exc())
    if settings.debug and not settings.is_production:
        return HTMLResponse(
            content=(
                "<h1>Internal Server Error</h1>"
                "<pre style='white-space:pre-wrap;font-size:12px'>"
                f"{traceback.format_exc()}"
                "</pre>"
            ),
            status_code=500,
        )
    if _wants_html(request):
        return _error_page(request, 500)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur. Consultez les journaux."},
    )


@app.get("/", response_class=HTMLResponse)
@app.get("/presentation", response_class=HTMLResponse)
def presentation(request: Request):
    """Public page to share with prospective hosts: what the platform does and what it costs."""
    from app.services.packs import PACKS, TOPUP, TRIAL
    from app.templating import templates

    return templates.TemplateResponse(
        request, "landing.html", {"packs": list(PACKS.values()), "topup": TOPUP, "trial": TRIAL}
    )


@app.get("/health")
def health():
    return {"status": "ok"}
