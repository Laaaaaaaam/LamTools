__author__ = "霖二 @Laaaaaaaam"
__copyright__ = "Copyright (c) 2026 霖二 @Laaaaaaaam"
__license__ = "MIT"
__email__ = "2667605815@qq.com"

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from fastapi import Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from starlette.middleware.base import BaseHTTPMiddleware

from lamtools_core.app import create_app
from lamtools_core.member import MemberManifest

from app.config import settings
from app.core.context import SessionFilter, session_id_var
from app.database import init_db
from app.routers import api_provider, billing, reference, dashboard, session, settings as settings_router, download, long_task
from app.routers import core_http


def _setup_logging():
    from app.core.context import SessionFilter

    session_filter = SessionFilter()

    log_file = settings.LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | [%(session_id)s] %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    file_handler.addFilter(session_filter)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | [%(session_id)s] %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    ))
    console_handler.addFilter(session_filter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


_setup_logging()


class SessionIdMiddleware(BaseHTTPMiddleware):
    """Extract session_id from URL path and set ContextVar for structured logging."""

    async def dispatch(self, request: Request, call_next):
        from app.core.context import session_id_var

        # Match paths like /api/sessions/{session_id}/...
        parts = request.url.path.strip("/").split("/")
        sid = "-"
        try:
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "sessions":
                sid = parts[2]
        except (IndexError, ValueError):
            pass

        token = session_id_var.set(sid)
        try:
            return await call_next(request)
        finally:
            session_id_var.reset(token)


# ---------------------------------------------------------------------------
# Artist member manifest
# ---------------------------------------------------------------------------

imager_manifest = MemberManifest(
    id="artist",
    name="lamartist",
    version=settings.APP_VERSION,
    display_name="AI Image Generation Manager",
    capabilities=["image_generation", "artist_runtime", "lineage_management"],
    default_routes={
        "/api/providers": "API provider management",
        "/api/billing": "Billing records",
        "/api/reference": "Reference images",
        "/api/dashboard": "Dashboard statistics",
        "/api/sessions": "Session management",
        "/api/settings": "Application settings",
        "/api/download": "Download tasks",
        "/api/long-task": "Long-running tasks",
    },
    hooks={},
)


# ---------------------------------------------------------------------------
# Health payload factory
# ---------------------------------------------------------------------------

def _get_health_payload() -> dict:
    """Return health check payload matching original Artist format."""
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "author": settings.APP_AUTHOR,
        "license": "MIT",
    }


# ---------------------------------------------------------------------------
# Create app using Core factory
# ---------------------------------------------------------------------------

app = create_app(
    members=[imager_manifest],
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    on_startup=[init_db],
    health_payload=_get_health_payload,
    enable_core_routes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionIdMiddleware)

app.include_router(api_provider.router)
app.include_router(billing.router)
app.include_router(reference.router)
app.include_router(dashboard.router)
app.include_router(session.router)
app.include_router(settings_router.router)
app.include_router(download.router)
app.include_router(long_task.router)
app.include_router(core_http.router, prefix="/api/core")


static_dir: Path = settings.STATIC_DIR

@app.get("/api/images/proxy")
async def proxy_image(url: str):
    decoded = unquote(url)
    parsed = urlparse(decoded)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only HTTP/HTTPS URLs are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        resolved_ip = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for family, *_, sockaddr in resolved_ip:
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local:
                raise HTTPException(status_code=403, detail="Access to private/internal addresses is not allowed")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(decoded, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=502, detail=f"Upstream returned {resp.status}")
                content = await resp.read()
                content_type = resp.headers.get("Content-Type", "image/png")
                if not content_type.startswith("image/"):
                    raise HTTPException(status_code=403, detail="Only image content types are allowed")
                return Response(content=content, media_type=content_type)
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")

# Serve generated images from uploads directory
app.mount("/generated", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="generated")

if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        if request.url.path.startswith("/api"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        return FileResponse(static_dir / "index.html")

    @app.get("/")
    async def root():
        return FileResponse(static_dir / "index.html")
