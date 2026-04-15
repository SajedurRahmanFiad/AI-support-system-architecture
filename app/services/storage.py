from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.config import get_settings


def detect_attachment_type(mime_type: str, filename: str | None = None) -> str:
    lowered_name = (filename or "").lower()
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    if lowered_name.endswith((".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".m4a", ".aiff")):
        return "audio"
    if lowered_name.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")):
        return "image"
    return "file"


def save_upload(brand_id: int, upload: UploadFile) -> tuple[str, str]:
    settings = get_settings()
    data = upload.file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds {settings.max_upload_bytes} bytes.",
        )

    suffix = Path(upload.filename or "upload.bin").suffix or ".bin"
    today = datetime.now(timezone.utc)
    relative_path = Path(f"brand_{brand_id}") / f"{today:%Y}" / f"{today:%m}" / f"{uuid4().hex}{suffix}"
    absolute_path = settings.upload_path / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(data)
    return str(relative_path).replace("\\", "/"), upload.content_type or "application/octet-stream"


def read_file_bytes(storage_path: str) -> bytes:
    settings = get_settings()
    absolute_path = settings.upload_path / storage_path
    if not absolute_path.exists():
        raise FileNotFoundError(storage_path)
    return absolute_path.read_bytes()
