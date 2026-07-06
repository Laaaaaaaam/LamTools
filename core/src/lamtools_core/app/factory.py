"""LamTools Core application factory — assembles members into a FastAPI app."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import APIRouter, FastAPI

from ..member import MemberManifest, MemberRegistry


@asynccontextmanager
async def _lifespan(
    app: FastAPI,
    startup_hooks: list[Callable],
    shutdown_hooks: list[Callable],
) -> AsyncIterator[None]:
    # --- Startup ---
    for hook in startup_hooks:
        result = hook()
        if asyncio.iscoroutine(result):
            await result
    yield
    # --- Shutdown ---
    for hook in shutdown_hooks:
        result = hook()
        if asyncio.iscoroutine(result):
            await result


def create_app(
    *,
    members: list[MemberManifest] | None = None,
    member_routers: dict[str, APIRouter] | None = None,
    title: str = "LamTools Core",
    version: str = "0.1.0",
    on_startup: list[Callable] | None = None,
    on_shutdown: list[Callable] | None = None,
    enable_core_routes: bool = False,
    health_payload: dict[str, Any] | Callable[[], dict[str, Any]] | None = None,
) -> FastAPI:
    """Create and configure the LamTools Core FastAPI application.

    Args:
        members: List of member manifests to register.
        member_routers: Mapping of member id -> APIRouter to mount.
        title: Application title.
        version: Application version.
        on_startup: Additional startup hooks.
        on_shutdown: Additional shutdown hooks.
        enable_core_routes: When True, mount the core HTTP router at
            ``/api/core`` with session, event, provider, and usage routes.
        health_payload: Custom payload for /api/health endpoint. Can be a
            dict (returned directly) or a callable (called per request).
            If not provided, returns {"status": "ok"}.

    Returns:
        Configured FastAPI application instance.
    """
    registry = MemberRegistry()

    # Register all members
    for manifest in members or []:
        registry.register(manifest)

    # Collect hooks
    startup_hooks = list(on_startup or [])
    for manifest in registry:
        if "startup" in manifest.hooks:
            startup_hooks.append(manifest.hooks["startup"])

    shutdown_hooks = list(on_shutdown or [])
    for manifest in registry:
        if "shutdown" in manifest.hooks:
            shutdown_hooks.append(manifest.hooks["shutdown"])

    app = FastAPI(
        title=title,
        version=version,
        lifespan=lambda app: _lifespan(app, startup_hooks, shutdown_hooks),
    )

    # --- Core routes ---
    if health_payload is not None:
        _hp = health_payload

        @app.get("/api/health")
        async def health() -> dict[str, Any]:
            return _hp() if callable(_hp) else _hp
    else:

        @app.get("/api/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

    @app.get("/api/members")
    async def list_members() -> list[dict[str, Any]]:
        return [m.to_dict() for m in registry]

    # --- Mount member routers ---
    routers = member_routers or {}
    for member_id, router in routers.items():
        prefix = f"/api/{member_id}"
        app.include_router(router, prefix=prefix)

    # --- Mount core routes (optional) ---
    if enable_core_routes:
        from ..http import create_core_router

        core_router = create_core_router()
        app.include_router(core_router, prefix="/api/core")

    # Store registry on app state for external access
    app.state.member_registry = registry

    return app


__all__ = ["create_app"]
