from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.attachment import WriterAttachment
from app.services.attachment_service import (
    attachment_to_dict,
    create_attachment_from_bytes,
    get_attachment_response,
    get_session_or_404,
    list_session_attachment_responses,
    open_attachment_response,
    open_with_default_app,
    preview_attachment_response,
)

router = APIRouter()


class AttachmentResponse(BaseModel):
    id: str
    project_id: str | None = None
    session_id: str
    message_id: str | None = None
    source: str
    agent_name: str | None = None
    filename: str
    label: str
    mime_type: str
    size: int
    preview_type: str
    metadata: dict = {}
    created_at: str


class AttachmentPreviewResponse(BaseModel):
    id: str
    filename: str
    preview_type: str
    mime_type: str
    text: str | None = None


@router.post("/sessions/{session_id}/attachments", response_model=AttachmentResponse)
async def upload_attachment(
    session_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session_or_404(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    content = await file.read()
    attachment = await create_attachment_from_bytes(
        db=db,
        session=session,
        filename=file.filename or "attachment",
        content=content,
        source="user_upload",
        mime_type=file.content_type,
    )
    await db.commit()
    await db.refresh(attachment)
    return attachment_to_dict(attachment)


@router.get("/sessions/{session_id}/attachments", response_model=list[AttachmentResponse])
async def list_session_attachments(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await list_session_attachment_responses(db, session_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/attachments/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await get_attachment_response(db, attachment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/attachments/{attachment_id}/preview", response_model=AttachmentPreviewResponse)
async def preview_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await preview_attachment_response(db, attachment_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
):
    attachment = await db.get(WriterAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = Path(attachment.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment file not found")
    return FileResponse(path, media_type=attachment.mime_type, filename=attachment.filename)


@router.post("/attachments/{attachment_id}/open")
async def open_attachment(
    attachment_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await open_attachment_response(db, attachment_id, opener=open_with_default_app)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
