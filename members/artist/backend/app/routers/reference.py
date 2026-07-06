import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.reference import ReferenceImageCreate, ReferenceImageResponse, ReferenceImageUpdate
from app.services.reference_manager import (
    add_reference,
    delete_reference,
    get_reference,
    list_references,
    reference_to_response,
    save_upload,
    update_reference,
)

router = APIRouter(prefix="/api/references", tags=["references"])


@router.post("/upload", response_model=ReferenceImageResponse)
async def api_upload_reference(
    file: UploadFile = File(...),
    name: str = "",
    is_global: bool = False,
    strength: float = 0.5,
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        upload_data = await save_upload(db, file.filename, content, file.content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    data = ReferenceImageCreate(name=name or file.filename, is_global=is_global, strength=strength)
    ref = await add_reference(db, upload_data, data)
    return reference_to_response(ref)


@router.get("", response_model=list[ReferenceImageResponse])
async def api_list_references(
    is_global: bool = None,
    db: AsyncSession = Depends(get_db),
):
    refs = await list_references(db, is_global)
    return [reference_to_response(r) for r in refs]


@router.get("/{ref_id}", response_model=ReferenceImageResponse)
async def api_get_reference(ref_id: str, db: AsyncSession = Depends(get_db)):
    ref = await get_reference(db, ref_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    return reference_to_response(ref)


@router.put("/{ref_id}", response_model=ReferenceImageResponse)
async def api_update_reference(
    ref_id: str, data: ReferenceImageUpdate, db: AsyncSession = Depends(get_db)
):
    ref = await update_reference(db, ref_id, data)
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    return reference_to_response(ref)


@router.delete("/{ref_id}")
async def api_delete_reference(ref_id: str, db: AsyncSession = Depends(get_db)):
    success = await delete_reference(db, ref_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reference not found")
    return {"message": "Reference deleted"}
