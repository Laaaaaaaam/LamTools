from __future__ import annotations

import secrets
from urllib.parse import urlparse

from app.config import settings


_CAPABILITY_TOKEN = secrets.token_urlsafe(32)


def issue_app_server_token() -> str:
    return _CAPABILITY_TOKEN


def is_allowed_browser_origin(origin: str | None) -> bool:
    if not origin:
        return True
    if origin in {"file://", "null"}:
        return True
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    if origin in settings.cors_origins:
        return True
    # Vite and desktop builds may run on a caller-selected local port. Keep the
    # trust boundary at loopback instead of pinning one development port.
    return parsed.port is not None


def is_authorized_websocket(origin: str | None, token: str | None) -> bool:
    if not origin:
        return True
    return is_allowed_browser_origin(origin) and secrets.compare_digest(token or "", _CAPABILITY_TOKEN)
