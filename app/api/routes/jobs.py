from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.jobs import JobOut, ProcessJobsRequest
from app.services.jobs import process_pending_jobs

router = APIRouter(prefix="/v1/jobs", dependencies=[Depends(require_platform_access)])


@router.get("", response_model=list[JobOut])
def list_jobs(db: DbSession, status_filter: str | None = None) -> list[models.Job]:
    statement = select(models.Job).order_by(models.Job.created_at.desc())
    if status_filter:
        statement = statement.where(models.Job.status == status_filter)
    return list(db.scalars(statement.limit(100)))


@router.post("/process-pending", response_model=list[JobOut])
def run_jobs(payload: ProcessJobsRequest, db: DbSession) -> list[models.Job]:
    return process_pending_jobs(db, payload.limit)
