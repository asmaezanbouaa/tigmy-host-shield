"""Compare guest form data against ID scan — Gemini (free), Ollama (local), or OpenAI."""

import base64
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from PIL import Image

from app.config import get_settings
from app.models import Submission
from app.services.id_preview import get_preview_image
from app.services.ai_local import verify_local_ocr
from app.services.storage import absolute_path


def _settings():
    return get_settings()


def _image_bytes_for_id(path: Path) -> tuple[bytes, str]:
    raw, _ = get_preview_image(path)
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    max_side = 1024
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75, optimize=True)
    return buf.getvalue(), "image/jpeg"


def _build_prompt(sub: Submission) -> str:
    return f"""You are verifying a guest registration for short-term rental in Morocco.
Compare the FORM DATA below with what is visible on the ID document image.

FORM DATA:
- Last name: {sub.last_name}
- First name: {sub.first_name}
- Date of birth: {sub.date_of_birth}
- Nationality: {sub.nationality}
- Country of residence: {sub.country_of_residence}
- ID document type: {sub.id_document_type}
- ID document number: {sub.id_document_number}

Reply with ONLY valid JSON (no markdown), this exact structure:
{{
  "overall": "match" | "partial" | "mismatch" | "unclear",
  "confidence": 0.0 to 1.0,
  "summary": "one short sentence for the host in English",
  "fields": [
    {{"field": "last_name", "form_value": "...", "id_value": "...", "status": "match"|"mismatch"|"missing"|"unclear"}},
    {{"field": "first_name", "form_value": "...", "id_value": "...", "status": "match"|"mismatch"|"missing"|"unclear"}},
    {{"field": "date_of_birth", "form_value": "...", "id_value": "...", "status": "match"|"mismatch"|"missing"|"unclear"}},
    {{"field": "nationality", "form_value": "...", "id_value": "...", "status": "match"|"mismatch"|"missing"|"unclear"}},
    {{"field": "id_document_number", "form_value": "...", "id_value": "...", "status": "match"|"mismatch"|"missing"|"unclear"}}
  ]
}}

Be tolerant of accents, order of names (Latin vs Arabic), and date format differences if the same date.
Flag mismatch only when clearly different."""


def _parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _parse_ai_response(text: str) -> dict:
    """Parse JSON from the model; fall back for small local models (e.g. moondream)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty response from AI model.")
    try:
        return _parse_json_response(text)
    except json.JSONDecodeError:
        low = text.lower()
        if any(w in low for w in ("mismatch", "not match", "different", "do not match")):
            overall = "mismatch"
        elif "partial" in low:
            overall = "partial"
        elif any(w in low for w in ("match", "matches", "same", "correct")):
            overall = "match"
        else:
            overall = "unclear"
        return {
            "overall": overall,
            "confidence": 0.55,
            "summary": text[:400],
            "fields": [],
            "parse_note": "Plain-text response (model did not return JSON).",
        }


def _finish_result(result: dict, model_name: str) -> dict:
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    result["model"] = model_name
    result["provider"] = _settings().ai_provider_normalized
    return result


def _config_hint() -> str:
    p = _settings().ai_provider_normalized
    if p == "gemini":
        return (
            "Set AI_PROVIDER=gemini and GEMINI_API_KEY in .env "
            "(free key: https://aistudio.google.com/apikey). "
            "Or use AI_PROVIDER=ollama for 100% free local AI."
        )
    if p == "local":
        return (
            "Set AI_PROVIDER=local in .env. Install: "
            "sudo apt install tesseract-ocr tesseract-ocr-fra && pip install pytesseract"
        )
    if p == "ollama":
        return (
            "Install Ollama, run: ollama pull moondream — then set AI_PROVIDER=ollama in .env"
        )
    if p == "openai":
        return (
            "OpenAI needs paid credits. For free: AI_PROVIDER=gemini or AI_PROVIDER=ollama"
        )
    return "Set AI_PROVIDER=gemini, ollama, or openai in .env"


def _verify_openai(sub: Submission, image_bytes: bytes, media_type: str) -> dict:
    if not _settings().openai_api_key.strip():
        raise ValueError(_config_hint())

    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    data_url = f"data:{media_type};base64,{b64}"
    payload = {
        "model": _settings().openai_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_prompt(sub)},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                ],
            }
        ],
        "max_tokens": 700,
        "temperature": 0.1,
    }
    cfg = _settings()
    url = f"{cfg.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.openai_api_key.strip()}",
        "Content-Type": "application/json",
    }
    timeout = httpx.Timeout(90.0, connect=15.0)
    with httpx.Client(timeout=timeout) as client:
        response = _post_with_retry(client, url, payload, headers)

    if response.status_code == 401:
        raise ValueError("Invalid OpenAI API key.")
    if response.status_code == 429:
        raise ValueError(
            "OpenAI quota exceeded (paid credits required). "
            "Switch to free AI in .env: AI_PROVIDER=gemini and GEMINI_API_KEY from "
            "https://aistudio.google.com/apikey — or AI_PROVIDER=ollama for local free AI."
        )
    if response.status_code != 200:
        raise ValueError(f"OpenAI error ({response.status_code}): {response.text[:300]}")

    content = response.json()["choices"][0]["message"]["content"]
    return _finish_result(_parse_ai_response(content), cfg.openai_model)


def _verify_gemini(sub: Submission, image_bytes: bytes, media_type: str) -> dict:
    cfg = _settings()
    key = cfg.gemini_api_key.strip()
    if not key:
        raise ValueError(_config_hint())

    model = cfg.gemini_model.strip()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": _build_prompt(sub)},
                    {"inline_data": {"mime_type": media_type, "data": b64}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800},
    }

    timeout = httpx.Timeout(90.0, connect=20.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload)
    except httpx.TimeoutException:
        raise ValueError("Gemini request timed out. Try again.") from None
    except httpx.RequestError as exc:
        raise ValueError(f"Cannot reach Gemini API: {exc}") from exc

    if response.status_code in (401, 403):
        raise ValueError(
            "Invalid Gemini API key. Get a free key at https://aistudio.google.com/apikey"
        )
    if response.status_code == 429:
        raise ValueError(
            f"Gemini free quota used for today. Active provider in .env: {_settings().ai_provider_normalized!r} "
            "(restart ./run.sh after changing .env). For free local AI: AI_PROVIDER=ollama"
        )
    if response.status_code != 200:
        err = response.text[:400]
        if "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
            raise ValueError(
                "Gemini free quota exceeded. Use AI_PROVIDER=ollama (install Ollama + ollama pull moondream)."
            )
        raise ValueError(f"Gemini error ({response.status_code}): {err}")

    data = response.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ValueError("Unexpected Gemini response format.") from exc

    return _finish_result(_parse_ai_response(text), model)


def _verify_ollama(sub: Submission, image_bytes: bytes, media_type: str) -> dict:
    cfg = _settings()
    base = cfg.ollama_base_url.rstrip("/")
    model = cfg.ollama_model.strip()
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": _build_prompt(sub),
                "images": [b64],
            }
        ],
        "stream": False,
        "options": {"temperature": 0.1},
    }

    timeout = httpx.Timeout(120.0, connect=5.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base}/api/chat", json=payload)
    except httpx.ConnectError:
        raise ValueError(
            "Ollama is not running. Install from https://ollama.com then run:\n"
            "  ollama pull moondream\n"
            "  ollama serve\n"
            "Set AI_PROVIDER=ollama in .env"
        ) from None
    except httpx.TimeoutException:
        raise ValueError("Ollama timed out (slow PC or large image). Try again.") from None
    except httpx.RequestError as exc:
        raise ValueError(f"Cannot reach Ollama at {base}: {exc}") from exc

    if response.status_code == 404:
        raise ValueError(
            f"Ollama model '{model}' not found. Run: ollama pull {model}"
        )
    if response.status_code != 200:
        raise ValueError(f"Ollama error ({response.status_code}): {response.text[:300]}")

    content = response.json().get("message", {}).get("content", "")
    if not content:
        raise ValueError("Empty response from Ollama. Try: ollama pull llava or moondream")

    return _finish_result(_parse_ai_response(content), f"ollama/{model}")


def _post_with_retry(
    client: httpx.Client,
    url: str,
    payload: dict,
    headers: dict,
    *,
    max_retries: int = 2,
) -> httpx.Response:
    response = None
    for attempt in range(max_retries + 1):
        response = client.post(url, json=payload, headers=headers)
        if response.status_code != 429 or attempt >= max_retries:
            return response
        wait = 8
        raw = response.headers.get("retry-after")
        if raw:
            try:
                wait = min(max(int(float(raw)), 3), 45)
            except ValueError:
                pass
        time.sleep(wait)
    return response  # type: ignore[return-value]


def verify_submission_id(sub: Submission) -> dict:
    cfg = _settings()
    if not cfg.ai_verification_enabled:
        raise ValueError(_config_hint())
    if not sub.id_document_path:
        raise ValueError("No ID document uploaded for this submission.")

    path = absolute_path(sub.id_document_path)
    if not path.exists():
        raise ValueError("ID document file is missing on disk.")

    image_bytes, media_type = _image_bytes_for_id(path)
    provider = cfg.ai_provider_normalized

    if provider == "local":
        return _finish_result(verify_local_ocr(sub, image_bytes), "local/tesseract")
    if provider == "gemini":
        return _verify_gemini(sub, image_bytes, media_type)
    if provider == "ollama":
        return _verify_ollama(sub, image_bytes, media_type)
    if provider == "openai":
        return _verify_openai(sub, image_bytes, media_type)

    raise ValueError(
        f"Unknown AI_PROVIDER={provider}. Use local, ollama, gemini, or openai."
    )


def save_verification_result(sub: Submission, result: dict) -> None:
    sub.ai_verification_json = json.dumps(result, ensure_ascii=False)
    sub.ai_verification_at = datetime.now(timezone.utc)


def load_verification_result(sub: Submission) -> dict | None:
    if not sub.ai_verification_json:
        return None
    try:
        return json.loads(sub.ai_verification_json)
    except json.JSONDecodeError:
        return None
