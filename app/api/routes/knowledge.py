from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app import models
from app.api.deps import DbSession, require_platform_access
from app.api.schemas.jobs import JobOut
from app.api.schemas.knowledge import (
    KnowledgeConversationExampleCreate,
    KnowledgeManualConversationExampleCreate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentOut,
    KnowledgeDocumentUpdate,
    KnowledgeReindexRequest,
    KnowledgeSearchHit,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services import knowledge
from app.services.brand_service import ensure_global_brand, get_brand_or_404, get_global_brand
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


@router.post("/conversation-examples", response_model=KnowledgeDocumentOut)
def create_conversation_example(payload: KnowledgeConversationExampleCreate, db: DbSession) -> models.KnowledgeDocument:
    return knowledge.upsert_conversation_example_document(
        db,
        build_llm_provider(),
        brand_id=payload.brand_id,
        conversation_id=payload.conversation_id,
        customer_message_id=payload.customer_message_id,
        assistant_message_id=payload.assistant_message_id,
        approved_reply=payload.approved_reply,
        title=payload.title,
        source_reference=payload.source_reference,
        notes=payload.notes,
        metadata=payload.metadata,
    )


@router.post("/manual-conversation-examples", response_model=KnowledgeDocumentOut)
def create_manual_conversation_example(payload: KnowledgeManualConversationExampleCreate, db: DbSession) -> models.KnowledgeDocument:
    target_brand_id = payload.brand_id
    if payload.global_example:
        target_brand_id = ensure_global_brand(db).id

    if payload.messages:
        return knowledge.create_manual_conversation_transcript_document(
            db,
            build_llm_provider(),
            brand_id=target_brand_id or 0,
            messages=[message.model_dump() for message in payload.messages],
            title=payload.title,
            source_reference=payload.source_reference,
            notes=payload.notes,
            metadata={
                **payload.metadata,
                **({"global_example": True} if payload.global_example else {}),
            },
        )

    return knowledge.create_manual_conversation_example_document(
        db,
        build_llm_provider(),
        brand_id=target_brand_id or 0,
        customer_text=payload.customer_text or "",
        approved_reply=payload.approved_reply or "",
        original_reply=payload.original_reply,
        title=payload.title,
        source_reference=payload.source_reference,
        notes=payload.notes,
        metadata={
            **payload.metadata,
            **({"global_example": True} if payload.global_example else {}),
        },
    )


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(db: DbSession, brand_id: int | None = None, global_only: bool = False) -> list[models.KnowledgeDocument]:
    if global_only:
        global_brand = get_global_brand(db)
        if not global_brand:
            return []
        return list(
            db.scalars(
                select(models.KnowledgeDocument)
                .where(models.KnowledgeDocument.brand_id == global_brand.id)
                .order_by(models.KnowledgeDocument.created_at.desc())
            )
        )

    if brand_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="brand_id is required unless global_only is true.")

    return list(
        db.scalars(
            select(models.KnowledgeDocument)
            .where(models.KnowledgeDocument.brand_id == brand_id)
            .order_by(models.KnowledgeDocument.created_at.desc())
        )
    )


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def get_document(document_id: int, db: DbSession) -> models.KnowledgeDocument:
    document = db.get(models.KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def update_document(payload: KnowledgeDocumentUpdate, document_id: int, db: DbSession) -> models.KnowledgeDocument:
    document = db.get(models.KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    changed_fields = payload.model_dump(exclude_unset=True)
    reindex_needed = False
    for field, value in changed_fields.items():
        if field == "metadata":
            document.metadata_json = value
        else:
            setattr(document, field, value)
        if field in {"title", "raw_text", "metadata"}:
            reindex_needed = True

    db.add(document)
    db.commit()
    db.refresh(document)

    if reindex_needed:
        return knowledge.index_document(db, build_llm_provider(), document)
    return document


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: DbSession) -> dict[str, str]:
    document = db.get(models.KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    db.delete(document)
    db.commit()
    return {"status": "deleted"}


@router.post("/documents/{document_id}/reindex", response_model=KnowledgeDocumentOut)
def reindex_document(document_id: int, payload: KnowledgeReindexRequest, db: DbSession) -> models.KnowledgeDocument:
    document = db.get(models.KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    get_brand_or_404(db, document.brand_id)
    if payload.process_async:
        document.status = "queued"
        db.add(document)
        db.commit()
        db.refresh(document)
        enqueue_job(db, "reindex_document", {"document_id": document.id}, document.brand_id)
        return document
    return knowledge.index_document(db, build_llm_provider(), document)


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
