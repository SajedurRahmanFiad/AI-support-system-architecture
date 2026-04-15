from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

platform_token_header = APIKeyHeader(name="X-Platform-Token", auto_error=False)
brand_token_header = APIKeyHeader(name="X-Brand-Api-Key", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def require_platform_access(token: str | None = Security(platform_token_header)) -> None:
    settings = get_settings()
    if not token or token != settings.platform_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing platform token.",
        )


def get_brand_token(token: str | None = Security(brand_token_header)) -> str | None:
    return token
