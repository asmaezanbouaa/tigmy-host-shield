import secrets


def generate_form_token() -> str:
    """Cryptographically secure token for guest form URLs (URL-safe, 43 chars)."""
    return secrets.token_urlsafe(32)
