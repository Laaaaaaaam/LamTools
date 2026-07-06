import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.services.settings_service import get_setting

FILENAME_WHITELIST = re.compile(r'^[\w\u4e00-\u9fff.\-]+$')

router = APIRouter(prefix="/api/download", tags=["download"])


class DownloadImageRequest(BaseModel):
    url: str
    filename: str = "image.png"


def get_default_download_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    return base / "downloads"


def _is_local_generated_url(url: str) -> bool:
    """Check if URL points to a locally generated image."""
    if "/generated/" not in url:
        return False
    try:
        parsed = urlparse(url)
        # Absolute localhost URLs
        host = parsed.hostname or ""
        if host in ("127.0.0.1", "localhost"):
            return True
        # Relative paths starting with /
        if parsed.scheme == "" and url.startswith("/generated/"):
            return True
    except Exception:
        pass
    return False


def _read_local_image(url: str) -> bytes | None:
    """Read a locally generated image from disk by its URL."""
    try:
        filename = url.rsplit("/", 1)[-1].split("?")[0]
        filepath = settings.UPLOAD_DIR / filename
        if filepath.exists():
            return filepath.read_bytes()
    except Exception:
        pass
    return None


@router.get("/default-path")
async def default_download_path():
    return {"path": str(get_default_download_dir())}


@router.post("/image")
async def download_image(req: DownloadImageRequest, db: AsyncSession = Depends(get_db)):
    dir_value = await get_setting(db, "download_directory")
    if dir_value and dir_value.get("value"):
        save_dir = Path(dir_value["value"])
    else:
        save_dir = get_default_download_dir()

    try:
        save_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"无法创建目录 {save_dir}: {e}", "path": str(save_dir)},
        )

    if not save_dir.is_dir():
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"路径不是目录: {save_dir}", "path": str(save_dir)},
        )

    if not FILENAME_WHITELIST.match(req.filename):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"非法文件名: {req.filename}"},
        )

    filepath = save_dir / req.filename
    resolved = filepath.resolve()
    if not resolved.is_relative_to(save_dir.resolve()):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"非法文件路径: {filepath}"},
        )

    counter = 1
    stem = filepath.stem
    suffix = filepath.suffix
    while filepath.exists():
        filepath = save_dir / f"{stem} ({counter}){suffix}"
        counter += 1

    # Local generated image: read from disk directly (fast, no HTTP self-loop)
    if _is_local_generated_url(req.url):
        content = _read_local_image(req.url)
        if content is None:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "本地图片文件不存在", "url": req.url},
            )
    else:
        # External URL: download via HTTP
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(req.url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        return JSONResponse(
                            status_code=502,
                            content={"success": False, "error": f"图片服务器返回 HTTP {resp.status}", "upstream_status": resp.status},
                        )
                    content = await resp.read()
        except aiohttp.ServerTimeoutError:
            return JSONResponse(
                status_code=502,
                content={"success": False, "error": "下载超时(30s)", "url": req.url},
            )
        except aiohttp.ClientConnectorError as e:
            return JSONResponse(
                status_code=502,
                content={"success": False, "error": f"无法连接到图片服务器: {e}", "url": req.url},
            )
        except aiohttp.ClientError as e:
            return JSONResponse(
                status_code=502,
                content={"success": False, "error": f"下载失败: {type(e).__name__}: {e}", "url": req.url},
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=502,
                content={"success": False, "error": "下载超时", "url": req.url},
            )

    try:
        filepath.write_bytes(content)
    except OSError as e:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": f"无法写入文件 {filepath}: {e}", "path": str(filepath)},
        )

    return {"success": True, "path": str(filepath), "size": len(content)}
