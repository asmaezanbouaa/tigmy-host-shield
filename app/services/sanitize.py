import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str, max_length: int = 2000) -> str:
    """Strip control chars and trim. Templates auto-escape on output."""
    if not isinstance(value, str):
        value = str(value)
    value = _CONTROL_CHARS.sub("", value).strip()
    if len(value) > max_length:
        value = value[:max_length]
    return value


def clean_optional(value: str | None, max_length: int = 255) -> str | None:
    if value is None:
        return None
    cleaned = clean_text(value, max_length)
    return cleaned if cleaned else None
