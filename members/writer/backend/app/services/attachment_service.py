from __future__ import annotations

import mimetypes
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import WriterAttachment
from app.models.base import gen_uuid
from app.models.session import WriterSession

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".log", ".xml", ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx",
    ".py", ".ps1", ".bat", ".sh", ".toml", ".ini", ".cfg", ".sql",
}
TEXT_MIME_PREFIXES = ("text/",)
TEXT_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
}


def attachment_to_dict(attachment: WriterAttachment) -> dict[str, Any]:
    return {
        "id": attachment.id,
        "project_id": attachment.project_id,
        "session_id": attachment.session_id,
        "message_id": attachment.message_id,
        "source": attachment.source,
        "agent_name": attachment.agent_name,
        "filename": attachment.filename,
        "label": attachment.filename,
        "mime_type": attachment.mime_type,
        "size": attachment.size,
        "preview_type": attachment.preview_type,
        "metadata": attachment.metadata_ or {},
        "created_at": attachment.created_at.isoformat() if attachment.created_at else "",
    }


async def list_session_attachment_responses(db: AsyncSession, session_id: str) -> list[dict[str, Any]]:
    session = await get_session_or_404(db, session_id)
    if session is None:
        raise LookupError("Session not found")
    result = await db.execute(
        select(WriterAttachment)
        .where(WriterAttachment.session_id == session_id)
        .order_by(WriterAttachment.created_at.asc())
    )
    return [attachment_to_dict(item) for item in result.scalars().all()]


async def get_attachment_response(db: AsyncSession, attachment_id: str) -> dict[str, Any]:
    attachment = await db.get(WriterAttachment, attachment_id)
    if attachment is None:
        raise LookupError("Attachment not found")
    return attachment_to_dict(attachment)


async def preview_attachment_response(db: AsyncSession, attachment_id: str) -> dict[str, Any]:
    attachment = await db.get(WriterAttachment, attachment_id)
    if attachment is None:
        raise LookupError("Attachment not found")
    path = Path(attachment.storage_path)
    if not path.exists():
        raise FileNotFoundError("Attachment file not found")
    text = read_text_preview(path) if attachment.preview_type == "text" else None
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "preview_type": attachment.preview_type,
        "mime_type": attachment.mime_type,
        "text": text,
    }


async def open_attachment_response(
    db: AsyncSession,
    attachment_id: str,
    *,
    opener: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    attachment = await db.get(WriterAttachment, attachment_id)
    if attachment is None:
        raise LookupError("Attachment not found")
    path = Path(attachment.storage_path)
    if not path.exists():
        raise FileNotFoundError("Attachment file not found")
    (opener or open_with_default_app)(path)
    return {"status": "opened", "id": attachment.id}


async def create_attachment_from_bytes(
    *,
    db: AsyncSession,
    session: WriterSession,
    filename: str,
    content: bytes,
    source: str,
    agent_name: str | None = None,
    mime_type: str | None = None,
    message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> WriterAttachment:
    safe_name = safe_filename(filename)
    root = attachment_dir(session.work_root, session.id)
    root.mkdir(parents=True, exist_ok=True)
    target = unique_path(root / safe_name)
    target.write_bytes(content)

    detected_mime = mime_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    attachment = WriterAttachment(
        id=gen_uuid(),
        project_id=session.project_id,
        session_id=session.id,
        message_id=message_id,
        source=source,
        agent_name=agent_name,
        filename=safe_name,
        mime_type=detected_mime,
        size=len(content),
        storage_path=str(target),
        preview_type=preview_type(safe_name, detected_mime),
        metadata_=metadata or {},
    )
    db.add(attachment)
    await db.flush()
    return attachment


async def get_session_or_404(db: AsyncSession, session_id: str) -> WriterSession | None:
    result = await db.execute(select(WriterSession).where(WriterSession.id == session_id))
    return result.scalar_one_or_none()


def read_text_preview(path: Path, limit: int = 200_000) -> str:
    data = path.read_bytes()
    if len(data) > limit:
        data = data[:limit]
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    if path.stat().st_size > limit:
        return f"{text}\n\n... 内容已截断，完整文件请用默认方式打开。"
    return text


def open_with_default_app(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def attachment_dir(work_root: str, session_id: str) -> Path:
    base = Path(work_root).resolve()
    return base / ".lamwriter" / "attachments" / session_id


def safe_filename(filename: str) -> str:
    name = Path(filename or "attachment").name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(". ")
    return name or "attachment"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem or "attachment"
    suffix = path.suffix
    for idx in range(2, 10_000):
        candidate = path.with_name(f"{stem}-{idx}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot allocate attachment filename: {path.name}")


def preview_type(filename: str, mime_type: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if mime_type in TEXT_MIME_TYPES or any(mime_type.startswith(prefix) for prefix in TEXT_MIME_PREFIXES):
        return "text"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type == "application/pdf":
        return "pdf"
    return "external"
