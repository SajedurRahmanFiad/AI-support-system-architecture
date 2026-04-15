from fastapi import APIRouter

from app.config import get_settings
from app.services.llm.factory import build_llm_provider
from app.services.speech import build_speech_provider

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    settings = get_settings()
    provider = build_llm_provider()
    speech_provider = build_speech_provider()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "llm_provider": provider.provider_name,
        "speech_provider": speech_provider.provider_name,
    }
