from __future__ import annotations

import os
import platform
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "__MEMBER_NAME__"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = __BACKEND_PORT__
    database_url: str = ""
    data_dir: str = ""
    cors_origins: list[str] = ["http://localhost:__FRONTEND_PORT__", "http://127.0.0.1:__FRONTEND_PORT__", "null"]

    model_config = {"env_file": ".env", "env_prefix": "__ENV_PREFIX___"}

    def model_post_init(self, __context) -> None:
        if not self.data_dir:
            if platform.system() == "Windows":
                base = Path(os.environ.get("APPDATA", Path.home()))
            elif platform.system() == "Darwin":
                base = Path.home() / "Library" / "Application Support"
            else:
                base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
            self.data_dir = str(base / "__MEMBER_NAME__")
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{Path(self.data_dir) / '__KEBAB_NAME__.db'}"


settings = Settings()
