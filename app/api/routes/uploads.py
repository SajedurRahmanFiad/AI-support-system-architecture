from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Security, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import brand_token_header, platform_token_header
from app.api.schemas.conversations import AttachmentOut
from app.api.schemas.messages import UploadResponse
from app.config import get_settings
from app.database import get_db
from app.services.brand_service import require_brand_access
from app.services.storage import detect_attachment_type, save_upload

router = APIRouter(prefix="/v1/uploads")


def _resolve_storage_path(storage_path: str) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path
    return get_settings().upload_path / path


@router.post("", response_model=UploadResponse)
def upload_attachment(
    brand_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> UploadResponse:
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    storage_path, mime_type = save_upload(brand_id, file)
    attachment = models.Attachment(
        brand_id=brand_id,
        attachment_type=detect_attachment_type(mime_type, file.filename),
        mime_type=mime_type,
        original_filename=file.filename,
        storage_path=storage_path,
        metadata_json={},
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return UploadResponse(attachment=attachment)


@router.get("", response_model=list[AttachmentOut])
def list_uploads(
    brand_id: int,
    limit: int = 200,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> list[models.Attachment]:
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    statement = (
        select(models.Attachment)
        .where(models.Attachment.brand_id == brand_id)
        .order_by(models.Attachment.created_at.desc())
        .limit(max(1, min(limit, 500)))
    )
    return list(db.scalars(statement))


@router.delete("/{attachment_id}")
def delete_upload(
    attachment_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> dict[str, str]:
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    attachment = db.get(models.Attachment, attachment_id)
    if not attachment or attachment.brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    file_path = _resolve_storage_path(attachment.storage_path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)
    db.delete(attachment)
    db.commit()
    return {"status": "deleted"}


@router.get("/{attachment_id}/download")
def download_upload(
    attachment_id: int,
    brand_id: int,
    db: Session = Depends(get_db),
    brand_token: str | None = Security(brand_token_header),
    platform_token: str | None = Security(platform_token_header),
) -> FileResponse:
    require_brand_access(db, brand_id, brand_token, platform_token, get_settings().platform_api_token)
    attachment = db.get(models.Attachment, attachment_id)
    if not attachment or attachment.brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
    file_path = _resolve_storage_path(attachment.storage_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found.")
    return FileResponse(
        path=file_path,
        media_type=attachment.mime_type,
        filename=attachment.original_filename or file_path.name,
    )
