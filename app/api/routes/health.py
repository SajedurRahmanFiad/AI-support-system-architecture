from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "gemini" and not settings.gemini_api_key:
        provider = "mock"
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "llm_provider": provider,
    }
