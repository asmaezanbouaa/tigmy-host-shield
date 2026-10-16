import time
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.services import fr
from app.services.packs import ORDER_STATUS_LABELS, PACKS, TOPUP, TRIAL

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(TEMPLATE_DIR))
    t.env.globals["app_name"] = get_settings().app_name
    # Changes on every app start, so browsers fetch fresh CSS/JS after an update
    t.env.globals["asset_v"] = str(int(time.time()))
    fr.register(t.env)
    t.env.globals.update({"PACKS": PACKS, "TOPUP": TOPUP, "TRIAL": TRIAL, "ORDER_STATUS_LABELS": ORDER_STATUS_LABELS})
    return t


templates = create_templates()
