from __future__ import annotations
import os
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.reference import ReferenceImage
from app.schemas.reference import ReferenceImageCreate, ReferenceImageUpdate

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_DOC_TYPES = {"text/plain", "application/json", "text/markdown"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".txt", ".md", ".json"}


async def save_upload(db: AsyncSession, file_name: str, file_content: bytes, file_type: str) -> dict:
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed")

    file_id = str(uuid.uuid4())
    stored_name = f"{file_id}{ext}"
    file_path = os.path.join(str(settings.UPLOAD_DIR), stored_name)

    with open(file_path, "wb") as f:
        f.write(file_content)

    thumbnail = ""
    if file_type.startswith("image/"):
        thumbnail = await _create_thumbnail(file_path, file_id, ext)

    return {
        "file_id": file_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_type": file_type,
        "file_size": len(file_content),
        "thumbnail": thumbnail,
    }


async def _create_thumbnail(file_path: str, file_id: str, ext: str) -> str:
    try:
        from PIL import Image as PILImage

        img = PILImage.open(file_path)
        img.thumbnail((200, 200))
        thumb_name = f"{file_id}_thumb{ext}"
        thumb_path = os.path.join(str(settings.UPLOAD_DIR), thumb_name)
        img.save(thumb_path)
        return thumb_path
    except Exception:
        return ""


async def delete_file(file_path: str) -> bool:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception:
        return False


async def add_reference(db: AsyncSession, upload_data: dict, data: ReferenceImageCreate) -> ReferenceImage:
    ref = ReferenceImage(
        name=data.name or upload_data["file_name"],
        file_path=upload_data["file_path"],
        file_type=upload_data["file_type"],
        file_size=upload_data["file_size"],
        thumbnail=upload_data.get("thumbnail", ""),
        is_global=data.is_global,
        strength=data.strength,
        crop_config=data.crop_config,
    )
    db.add(ref)
    await db.commit()
    await db.refresh(ref)
    return ref


async def update_reference(db: AsyncSession, ref_id: str, data: ReferenceImageUpdate) -> ReferenceImage | None:
    result = await db.execute(select(ReferenceImage).where(ReferenceImage.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ref, key, value)

    await db.commit()
    await db.refresh(ref)
    return ref


async def delete_reference(db: AsyncSession, ref_id: str) -> bool:
    result = await db.execute(select(ReferenceImage).where(ReferenceImage.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        return False
    await delete_file(ref.file_path)
    if ref.thumbnail:
        await delete_file(ref.thumbnail)
    await db.delete(ref)
    await db.commit()
    return True


async def list_references(db: AsyncSession, is_global: bool = None) -> list[ReferenceImage]:
    query = select(ReferenceImage)
    if is_global is not None:
        query = query.where(ReferenceImage.is_global == is_global)
    result = await db.execute(query.order_by(ReferenceImage.created_at.desc()))
    return list(result.scalars().all())


async def get_reference(db: AsyncSession, ref_id: str) -> ReferenceImage | None:
    result = await db.execute(select(ReferenceImage).where(ReferenceImage.id == ref_id))
    return result.scalar_one_or_none()


async def get_global_references(db: AsyncSession) -> list[ReferenceImage]:
    result = await db.execute(
        select(ReferenceImage).where(ReferenceImage.is_global == True).order_by(ReferenceImage.created_at.desc())
    )
    return list(result.scalars().all())


def reference_to_response(ref: ReferenceImage) -> dict:
    return {
        "id": ref.id,
        "name": ref.name,
        "file_path": ref.file_path,
        "file_type": ref.file_type,
        "file_size": ref.file_size,
        "thumbnail": ref.thumbnail,
        "is_global": ref.is_global,
        "strength": ref.strength,
        "crop_config": ref.crop_config or {},
        "created_at": ref.created_at,
    }
