from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Tigmi Host Shield"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "dev-secret-change-in-production"
    host: str = "0.0.0.0"
    port: int = 8000
    base_url: str = "http://localhost:8000"
    force_https: bool = False

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'guest_registry.db'}"

    # Under data/ so one Railway volume at /app/data keeps DB + uploads
    storage_path: Path = PROJECT_ROOT / "data" / "storage"
    signatures_dir: str = "signatures"
    pdfs_dir: str = "pdfs"
    id_documents_dir: str = "id_documents"
    archive_exports_dir: str = "archive_exports"
    receipts_dir: str = "receipts"

    id_retention_hours_after_verify: int = 14
    archive_purge_interval_days: int = 90

    session_cookie_name: str = "guest_registry_admin"
    session_max_age_hours: int = 24

    admin_username: str = "admin"
    admin_password: str = "changeme"
    admin_username_2: str = ""
    admin_password_2: str = ""

    default_link_expiry_days: int = 30

    rules_fr_path: Path = PROJECT_ROOT / "config" / "rules_fr.txt"
    rules_en_path: Path = PROJECT_ROOT / "config" / "rules_en.txt"
    rules_ar_path: Path = PROJECT_ROOT / "config" / "rules_ar.txt"

    # AI ID check: local (free OCR, unlimited) | gemini (free tier, daily limit) | openai (paid)
    ai_provider: str = "local"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    ai_auto_verify_on_submit: bool = True
    ai_auto_confirm_threshold: float = 0.8

    # Payment by bank transfer + support (kept in .env, never committed: the repository is public)
    bank_name: str = ""     # e.g. "CIH Bank"
    bank_branch: str = ""   # e.g. "Agence Guéliz Central, 187 bd Mohamed V"
    bank_holder: str = ""
    bank_rib: str = ""
    bank_iban: str = ""
    bank_swift: str = ""
    support_whatsapp: str = ""  # international format without "+", e.g. 2126xxxxxxxx

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    def production_problems(self) -> list[str]:
        """Settings that are unsafe to run with in production (guest IDs are stored here)."""
        problems = []
        if self.debug:
            problems.append("DEBUG must be false (it shows code errors to visitors)")
        if len(self.secret_key) < 32 or "change" in self.secret_key.lower():
            problems.append("SECRET_KEY must be a random string of 32+ characters")
        weak = {"changeme", "admin", "password", "your-secure-password"}
        for name, pw in (("ADMIN_PASSWORD", self.admin_password), ("ADMIN_PASSWORD_2", self.admin_password_2)):
            if name == "ADMIN_PASSWORD_2" and not self.admin_username_2.strip():
                continue
            if pw.strip().lower() in weak or len(pw) < 10:
                problems.append(f"{name} must be at least 10 characters and not a default")
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            problems.append("BASE_URL must be your public https:// address")
        return problems

    @property
    def ai_provider_normalized(self) -> str:
        return (self.ai_provider or "local").strip().lower()

    @property
    def ai_verification_enabled(self) -> bool:
        p = self.ai_provider_normalized
        if p in ("off", "none", "disabled", ""):
            return False
        if p == "gemini":
            return bool(self.gemini_api_key.strip())
        if p == "local":
            return True
        if p == "openai":
            return bool(self.openai_api_key.strip())
        return False

    @property
    def ai_provider_label(self) -> str:
        labels = {
            "local": "Local OCR (free, unlimited)",
            "gemini": "Google Gemini (free tier)",
            "openai": "OpenAI (paid credits)",
        }
        return labels.get(self.ai_provider_normalized, self.ai_provider_normalized)

    @property
    def signatures_path(self) -> Path:
        return self.storage_path / self.signatures_dir

    @property
    def pdfs_path(self) -> Path:
        return self.storage_path / self.pdfs_dir

    @property
    def id_documents_path(self) -> Path:
        return self.storage_path / self.id_documents_dir

    @property
    def archive_exports_path(self) -> Path:
        return self.storage_path / self.archive_exports_dir

    @property
    def receipts_path(self) -> Path:
        return self.storage_path / self.receipts_dir

    def load_rules_fr(self) -> str:
        if self.rules_fr_path.exists():
            return self.rules_fr_path.read_text(encoding="utf-8")
        return ""

    def load_rules_en(self) -> str:
        if self.rules_en_path.exists():
            return self.rules_en_path.read_text(encoding="utf-8")
        return ""

    def load_rules_ar(self) -> str:
        if self.rules_ar_path.exists():
            return self.rules_ar_path.read_text(encoding="utf-8")
        return ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
