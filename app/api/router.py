from fastapi import APIRouter

from app.api.routes import (
    audit_logs,
    brand_prompt_config,
    brands,
    conversations,
    customers,
    dashboard,
    feedback,
    health,
    jobs,
    knowledge,
    messages,
    products,
    uploads,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(audit_logs.router, tags=["audit-logs"])
api_router.include_router(dashboard.router, tags=["dashboard"])
api_router.include_router(brand_prompt_config.router, tags=["brand-prompt-config"])
api_router.include_router(brands.router, tags=["brands"])
api_router.include_router(knowledge.router, tags=["knowledge"])
api_router.include_router(products.router, tags=["products"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(messages.router, tags=["messages"])
api_router.include_router(feedback.router, tags=["feedback"])
api_router.include_router(customers.router, tags=["customers"])
api_router.include_router(conversations.router, tags=["conversations"])
api_router.include_router(jobs.router, tags=["jobs"])
