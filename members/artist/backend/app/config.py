import os
import platform
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _get_platform_data_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "lamartist"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "lamartist"
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / "lamartist"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    APP_NAME: str = "lamartist"
    APP_VERSION: str = "0.4.0-alpha"
    APP_AUTHOR: str = "霖二 @Laaaaaaaam"
    APP_AUTHOR_EMAIL: str = "2667605815@qq.com"
    DEBUG: bool = True

    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    DATA_DIR: Path = Path(os.environ.get("LAMARTIST_DATA_DIR", "")) if os.environ.get("LAMARTIST_DATA_DIR") else _get_platform_data_dir()
    STATIC_DIR: Path = Path(os.environ.get("LAMARTIST_STATIC_DIR", "")) if os.environ.get("LAMARTIST_STATIC_DIR") else BASE_DIR / "frontend" / "dist"
    UPLOAD_DIR: Path = DATA_DIR / "uploads"
    DB_PATH: Path = DATA_DIR / "lamartist.db"

    DB_URL: str = ""
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174", "http://localhost", "http://127.0.0.1"]

    LOG_LEVEL: str = "INFO"
    LOG_FILE: Path = DATA_DIR / "lamartist.log"

    # 运行时端口，由启动脚本写入（uvicorn --port / desktop server.py）
    # 用于生成图片等资源的绝对 URL
    SERVER_PORT: int = 6171

    def model_post_init(self, __context):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not self.DB_URL:
            self.DB_URL = f"sqlite+aiosqlite:///{self.DB_PATH}"


settings = Settings()
