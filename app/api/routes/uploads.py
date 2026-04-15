from fastapi import APIRouter, Depends, File, Form, Security, UploadFile
from sqlalchemy.orm import Session

from app import models
from app.api.deps import brand_token_header, platform_token_header
from app.api.schemas.messages import UploadResponse
from app.config import get_settings
from app.database import get_db
from app.services.brand_service import require_brand_access
from app.services.storage import detect_attachment_type, save_upload

router = APIRouter(prefix="/v1/uploads")


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
        attachment_type=detect_attachment_type(mime_type),
        mime_type=mime_type,
        original_filename=file.filename,
        storage_path=storage_path,
        metadata_json={},
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return UploadResponse(attachment=attachment)
