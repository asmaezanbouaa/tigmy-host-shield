from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import get_settings

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def create_templates() -> Jinja2Templates:
    t = Jinja2Templates(directory=str(TEMPLATE_DIR))
    t.env.globals["app_name"] = get_settings().app_name
    return t


templates = create_templates()
