"""Bootstrap endpoint providing initial app state and configuration."""

from __future__ import annotations

from pydantic import BaseModel

from app.api.deps import DbSession, require_platform_access
from app.api.routes.dashboard import (
    _brand_options,
    _conversation_counts,
    _group_counts,
    get_dashboard_overview,
)
from app.api.schemas.dashboard import (
    BrandOptionOut,
    DashboardOverviewOut,
)
from app.config import get_settings
from fastapi import APIRouter, Depends

router = APIRouter()


class SessionState(BaseModel):
    """Authentication session state."""
    authenticated: bool
    user: dict | None = None
    csrf_token: str | None = None


class SettingsState(BaseModel):
    """Application settings exposed to frontend."""
    app_name: str
    admin_email: str = ""
    default_brand_id: int | None = None
    auto_refresh_seconds: int = 30


class BootstrapPayload(BaseModel):
    """Complete bootstrap payload for app initialization."""
    session: SessionState
    settings: SettingsState | None = None
    brand_options: list[BrandOptionOut] = []
    overview: DashboardOverviewOut | None = None


@router.get("/bootstrap", response_model=BootstrapPayload)
def get_bootstrap(db: DbSession) -> BootstrapPayload:
    """
    Bootstrap endpoint providing initial app state.
    
    Returns:
    - Session information (authenticated status, user, csrf token)
    - App settings (app name, admin email, defaults)
    - Available brands for selection
    - Dashboard overview data
    """
    settings = get_settings()
    
    # Get dashboard overview (includes brand options)
    overview = get_dashboard_overview(db)
    
    # Prepare settings state
    settings_state = SettingsState(
        app_name=settings.app_name,
        admin_email="",  # Could be populated from database if available
        default_brand_id=None,  # Could be set from database preferences
        auto_refresh_seconds=30,
    )
    
    # Session state - would need proper auth implementation
    # For now, return authenticated=false and no user
    session_state = SessionState(
        authenticated=False,
        user=None,
        csrf_token=None,
    )
    
    return BootstrapPayload(
        session=session_state,
        settings=settings_state,
        brand_options=overview.brand_options,
        overview=overview,
    )


@router.get("/overview", response_model=DashboardOverviewOut)
def get_overview(db: DbSession) -> DashboardOverviewOut:
    """
    Overview endpoint - alias to dashboard overview.
    
    Returns overview statistics including:
    - Totals (brands, conversations, handoffs, jobs, feedback)
    - Health status
    - Recent jobs
    - Conversation chart data
    - Available brands
    """
    return get_dashboard_overview(db)
