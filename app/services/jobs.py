from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.api.schemas.messages import MessageProcessRequest
from app.services import knowledge
from app.services.llm.factory import build_llm_provider
from app.services.orchestrator import MessageProcessor


def enqueue_job(db: Session, kind: str, payload: dict, brand_id: int | None = None) -> models.Job:
    job = models.Job(
        brand_id=brand_id,
        kind=kind,
        status="pending",
        payload_json=payload,
        available_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_pending_jobs(db: Session, limit: int = 10) -> list[models.Job]:
    now = datetime.now(timezone.utc)
    statement = (
        select(models.Job)
        .where(models.Job.status == "pending")
        .where(or_(models.Job.available_at.is_(None), models.Job.available_at <= now))
        .order_by(models.Job.created_at.asc())
        .limit(limit)
    )
    jobs = list(db.scalars(statement))
    results: list[models.Job] = []

    for job in jobs:
        job.status = "running"
        job.locked_at = now
        job.attempts += 1
        db.add(job)
        db.commit()

        try:
            if job.kind == "process_message":
                payload = MessageProcessRequest.model_validate(job.payload_json or {})
                result = MessageProcessor(db).process(payload)
                job.result_json = result.model_dump()
            elif job.kind == "reindex_document":
                document_id = int((job.payload_json or {}).get("document_id", 0))
                document = db.get(models.KnowledgeDocument, document_id)
                if not document:
                    raise ValueError("Document not found for job.")
                brand = db.get(models.Brand, document.brand_id)
                knowledge.index_document(db, build_llm_provider(brand), document)
                job.result_json = {"document_id": document.id, "status": document.status}
            else:
                raise ValueError(f"Unsupported job kind: {job.kind}")
            job.status = "completed"
            job.last_error = None
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(models.Job, job.id) or job
            job.status = "failed"
            job.last_error = str(exc)
        finally:
            job.locked_at = None
            db.add(job)
            db.commit()
            db.refresh(job)
            results.append(job)
    return results
