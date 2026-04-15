from fastapi import APIRouter, Depends
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.jobs import JobOut
from app.api.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentOut,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services import knowledge
from app.services.jobs import enqueue_job
from app.services.llm.factory import build_llm_provider

router = APIRouter(prefix="/v1/knowledge", dependencies=[Depends(require_platform_access)])


@router.post("/documents", response_model=KnowledgeDocumentOut)
def create_document(payload: KnowledgeDocumentCreate, db: DbSession) -> models.KnowledgeDocument:
    document = models.KnowledgeDocument(
        brand_id=payload.brand_id,
        title=payload.title,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        raw_text=payload.raw_text,
        metadata_json=payload.metadata,
        status="queued" if payload.process_async else "ready",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    if payload.process_async:
        enqueue_job(db, "reindex_document", {"document_id": document.id}, payload.brand_id)
        return document

    provider = build_llm_provider()
    return knowledge.index_document(db, provider, document)


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(brand_id: int, db: DbSession) -> list[models.KnowledgeDocument]:
    return list(
        db.scalars(
            select(models.KnowledgeDocument)
            .where(models.KnowledgeDocument.brand_id == brand_id)
            .order_by(models.KnowledgeDocument.created_at.desc())
        )
    )


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_documents(payload: KnowledgeSearchRequest, db: DbSession) -> KnowledgeSearchResponse:
    hits = knowledge.search_knowledge(db, build_llm_provider(), payload.brand_id, payload.query, payload.top_k)
    return KnowledgeSearchResponse(
        hits=[
            KnowledgeSearchHit(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                title=item.title,
                content=item.content,
                score=item.score,
            )
            for item in hits
        ]
    )
