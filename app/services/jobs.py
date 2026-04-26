from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import threading
import time

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app import models
from app.api.schemas.messages import MessageProcessRequest
from app.config import get_settings
from app.database import SessionLocal
from app.services import knowledge
from app.services.llm.factory import build_llm_provider
from app.services.message_delivery import deliver_external_reply_if_needed
from app.services.orchestrator import MessageProcessor


def enqueue_job(
    db: Session,
    kind: str,
    payload: dict,
    brand_id: int | None = None,
    *,
    available_at: datetime | None = None,
) -> models.Job:
    job = models.Job(
        brand_id=brand_id,
        kind=kind,
        status="pending",
        payload_json=payload,
        available_at=available_at or datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def process_pending_jobs(db: Session, limit: int = 10, max_concurrency: int | None = None) -> list[models.Job]:
    settings = get_settings()
    worker_count = max(1, min(max_concurrency or settings.job_runner_max_concurrency, limit))
    claimed_job_ids = _claim_pending_job_ids(db, limit)
    if not claimed_job_ids:
        return []

    processed_ids: list[int] = []
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="job-runner") as executor:
        futures = {executor.submit(_process_job, job_id): job_id for job_id in claimed_job_ids}
        for future in as_completed(futures):
            job_id = futures[future]
            try:
                processed_ids.append(future.result())
            except Exception as exc:  # noqa: BLE001
                print(f"[job-runner] job={job_id} crashed: {exc}", flush=True)
                processed_ids.append(job_id)

    refreshed_jobs: list[models.Job] = []
    for job_id in processed_ids:
        job = db.get(models.Job, job_id)
        if job is not None:
            refreshed_jobs.append(job)
    refreshed_jobs.sort(key=lambda item: item.id)
    return refreshed_jobs


def _claim_pending_job_ids(db: Session, limit: int) -> list[int]:
    now = datetime.now(timezone.utc)
    statement = (
        select(models.Job.id)
        .where(models.Job.status == "pending")
        .where(or_(models.Job.available_at.is_(None), models.Job.available_at <= now))
        .order_by(models.Job.created_at.asc())
        .limit(limit)
    )
    candidate_ids = list(db.scalars(statement))
    claimed_ids: list[int] = []

    for job_id in candidate_ids:
        result = db.execute(
            update(models.Job)
            .where(models.Job.id == job_id, models.Job.status == "pending")
            .values(
                status="running",
                locked_at=now,
                attempts=models.Job.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            claimed_ids.append(job_id)

    db.commit()
    return claimed_ids


def _process_job(job_id: int) -> int:
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(models.Job, job_id)
        if job is None:
            return job_id

        try:
            if job.kind == "process_message":
                payload = MessageProcessRequest.model_validate(job.payload_json or {})
                result = MessageProcessor(db).process(payload)
                delivery = deliver_external_reply_if_needed(db, payload, result)
                job.result_json = {
                    **result.model_dump(),
                    "delivery": delivery,
                }
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
            job.available_at = None
            print(f"[job-runner] job={job.id} kind={job.kind} status=completed", flush=True)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(models.Job, job_id) or job
            retry_delay = max(0, settings.job_retry_delay_seconds)
            should_retry = job.attempts < max(1, settings.job_retry_limit)
            job.last_error = str(exc)
            job.available_at = (
                datetime.now(timezone.utc) + timedelta(seconds=retry_delay)
                if should_retry and retry_delay > 0
                else datetime.now(timezone.utc)
            )
            job.status = "pending" if should_retry else "failed"
            print(
                f"[job-runner] job={job.id} kind={job.kind} status={job.status} attempts={job.attempts} error={exc}",
                flush=True,
            )
        finally:
            job.locked_at = None
            db.add(job)
            db.commit()
            db.refresh(job)

    return job_id


class BackgroundJobRunner:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.settings.job_runner_enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="background-job-runner", daemon=True)
        self._thread.start()
        print(
            f"[job-runner] started poll={self.settings.job_runner_poll_interval_seconds}s batch={self.settings.job_runner_batch_size} concurrency={self.settings.job_runner_max_concurrency}",
            flush=True,
        )

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5)
        self._thread = None
        print("[job-runner] stopped", flush=True)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with SessionLocal() as db:
                    process_pending_jobs(
                        db,
                        limit=self.settings.job_runner_batch_size,
                        max_concurrency=self.settings.job_runner_max_concurrency,
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[job-runner] loop error: {exc}", flush=True)

            self._stop_event.wait(max(0.2, self.settings.job_runner_poll_interval_seconds))
