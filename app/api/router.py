from fastapi import APIRouter

from app.api.routes import brands, conversations, customers, health, jobs, knowledge, messages, uploads

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(brands.router, tags=["brands"])
api_router.include_router(knowledge.router, tags=["knowledge"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(messages.router, tags=["messages"])
api_router.include_router(customers.router, tags=["customers"])
api_router.include_router(conversations.router, tags=["conversations"])
api_router.include_router(jobs.router, tags=["jobs"])
