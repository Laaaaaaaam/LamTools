from fastapi.middleware.cors import CORSMiddleware

from lamtools_core.app import create_app

from app.config import settings
from app.member import manifest


def _health_payload() -> dict:
    return {"status": "ok", "app": settings.app_name}

app = create_app(
    members=[manifest],
    title="__MEMBER_NAME__",
    version="0.1.0",
    enable_core_routes=True,
    health_payload=_health_payload,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
