from __future__ import annotations

import math

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app import models
from app.config import get_settings
from app.services.llm.base import KnowledgeSnippet, LLMProvider


def chunk_text(raw_text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    normalized = " ".join(raw_text.split())
    if len(normalized) <= chunk_size:
        return [normalized]
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(0, end - overlap)
    return chunks


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


def _truncate_title(text: str, max_length: int = 72) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 1].rstrip()}…"


def _build_conversation_example_text(
    customer_text: str,
    approved_reply: str,
    original_reply: str | None = None,
    notes: str | None = None,
) -> str:
    sections = [
        "Approved support example captured from a real customer conversation.",
        f"Customer message:\n{customer_text.strip()}",
        f"Approved reply:\n{approved_reply.strip()}",
    ]
    if original_reply and original_reply.strip() and original_reply.strip() != approved_reply.strip():
        sections.append(f"Original reply draft:\n{original_reply.strip()}")
    if notes and notes.strip():
        sections.append(f"Reviewer notes:\n{notes.strip()}")
    sections.append(
        "Use this example only when a future customer asks for materially similar help and the facts still match the current policy, catalog, or workflow."
    )
    return "\n\n".join(sections)


def index_document(db: Session, provider: LLMProvider, document: models.KnowledgeDocument) -> models.KnowledgeDocument:
    db.execute(delete(models.KnowledgeChunk).where(models.KnowledgeChunk.document_id == document.id))
    db.flush()

    chunks = chunk_text(document.raw_text)
    embeddings = provider.embed_texts(chunks)
    for index, chunk in enumerate(chunks):
        db.add(
            models.KnowledgeChunk(
                brand_id=document.brand_id,
                document_id=document.id,
                chunk_index=index,
                content=chunk,
                token_estimate=estimate_tokens(chunk),
                embedding_json=embeddings[index] if index < len(embeddings) else None,
                metadata_json={"title": document.title},
            )
        )
    document.status = "ready"
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def upsert_conversation_example_document(
    db: Session,
    provider: LLMProvider,
    *,
    brand_id: int,
    conversation_id: int,
    customer_message_id: int,
    approved_reply: str,
    assistant_message_id: int | None = None,
    title: str | None = None,
    source_reference: str | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> models.KnowledgeDocument:
    conversation = db.get(models.Conversation, conversation_id)
    if not conversation or conversation.brand_id != brand_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")

    customer_message = db.get(models.Message, customer_message_id)
    if (
        not customer_message
        or customer_message.brand_id != brand_id
        or customer_message.conversation_id != conversation_id
        or customer_message.role != "customer"
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Customer message not found in this conversation.")

    approved_reply_text = approved_reply.strip()
    if not approved_reply_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approved_reply is required.")

    assistant_message: models.Message | None = None
    if assistant_message_id is not None:
        assistant_message = db.get(models.Message, assistant_message_id)
        if (
            not assistant_message
            or assistant_message.brand_id != brand_id
            or assistant_message.conversation_id != conversation_id
            or assistant_message.role != "assistant"
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assistant message not found in this conversation.")
    else:
        assistant_message = db.scalar(
            select(models.Message)
            .where(
                models.Message.brand_id == brand_id,
                models.Message.conversation_id == conversation_id,
                models.Message.role == "assistant",
                models.Message.created_at >= customer_message.created_at,
            )
            .order_by(models.Message.created_at.asc())
            .limit(1)
        )

    document_title = (title or "").strip() or f"Conversation Example: {_truncate_title(customer_message.text)}"
    reference = (source_reference or "").strip() or f"conversation:{conversation_id}/customer:{customer_message_id}"
    document_metadata = dict(metadata or {})
    document_metadata.update(
        {
            "training_type": "conversation_rag_example",
            "conversation_id": conversation_id,
            "customer_message_id": customer_message_id,
            "assistant_message_id": assistant_message.id if assistant_message else assistant_message_id,
            "customer_message_text": customer_message.text.strip(),
            "approved_reply": approved_reply_text,
            "original_reply": assistant_message.text.strip() if assistant_message and assistant_message.text else None,
            "notes": notes.strip() if notes else None,
        }
    )

    raw_text = _build_conversation_example_text(
        customer_text=customer_message.text,
        approved_reply=approved_reply_text,
        original_reply=assistant_message.text if assistant_message else None,
        notes=notes,
    )

    existing_document = next(
        (
            document
            for document in db.scalars(
                select(models.KnowledgeDocument).where(
                    models.KnowledgeDocument.brand_id == brand_id,
                    models.KnowledgeDocument.source_type == "conversation_training",
                )
            )
            if (document.metadata_json or {}).get("conversation_id") == conversation_id
            and (document.metadata_json or {}).get("customer_message_id") == customer_message_id
        ),
        None,
    )

    if existing_document:
        existing_document.title = document_title
        existing_document.source_reference = reference
        existing_document.raw_text = raw_text
        existing_document.metadata_json = document_metadata
        existing_document.status = "ready"
        db.add(existing_document)
        db.commit()
        db.refresh(existing_document)
        return index_document(db, provider, existing_document)

    document = models.KnowledgeDocument(
        brand_id=brand_id,
        title=document_title,
        source_type="conversation_training",
        source_reference=reference,
        raw_text=raw_text,
        metadata_json=document_metadata,
        status="ready",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return index_document(db, provider, document)


def create_manual_conversation_example_document(
    db: Session,
    provider: LLMProvider,
    *,
    brand_id: int,
    customer_text: str,
    approved_reply: str,
    original_reply: str | None = None,
    title: str | None = None,
    source_reference: str | None = None,
    notes: str | None = None,
    metadata: dict | None = None,
) -> models.KnowledgeDocument:
    customer_text_value = customer_text.strip()
    approved_reply_value = approved_reply.strip()
    original_reply_value = original_reply.strip() if original_reply and original_reply.strip() else None
    notes_value = notes.strip() if notes and notes.strip() else None

    if not customer_text_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="customer_text is required.")
    if not approved_reply_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="approved_reply is required.")

    document_title = (title or "").strip() or f"Conversation Example: {_truncate_title(customer_text_value)}"
    reference = (source_reference or "").strip() or "manual:dashboard-training"
    document_metadata = dict(metadata or {})
    document_metadata.update(
        {
            "training_type": "manual_conversation_rag_example",
            "customer_message_text": customer_text_value,
            "approved_reply": approved_reply_value,
            "original_reply": original_reply_value,
            "notes": notes_value,
        }
    )

    raw_text = _build_conversation_example_text(
        customer_text=customer_text_value,
        approved_reply=approved_reply_value,
        original_reply=original_reply_value,
        notes=notes_value,
    )

    document = models.KnowledgeDocument(
        brand_id=brand_id,
        title=document_title,
        source_type="conversation_training",
        source_reference=reference,
        raw_text=raw_text,
        metadata_json=document_metadata,
        status="ready",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return index_document(db, provider, document)


def lexical_score(query: str, text: str) -> float:
    query_words = {item.lower().strip(".,!?") for item in query.split() if len(item) > 2}
    text_words = {item.lower().strip(".,!?") for item in text.split()}
    if not query_words:
        return 0.0
    return len(query_words & text_words) / len(query_words)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def search_knowledge(
    db: Session,
    provider: LLMProvider,
    brand_id: int,
    query: str,
    top_k: int | None = None,
) -> list[KnowledgeSnippet]:
    settings = get_settings()
    top_k = top_k or settings.knowledge_top_k
    statement = (
        select(models.KnowledgeChunk)
        .options(joinedload(models.KnowledgeChunk.document))
        .where(models.KnowledgeChunk.brand_id == brand_id)
        .limit(settings.knowledge_scan_limit)
    )
    chunks = list(db.scalars(statement))
    if not chunks:
        return []

    query_embedding_list = provider.embed_texts([query])
    query_embedding = query_embedding_list[0] if query_embedding_list else None

    scored: list[KnowledgeSnippet] = []
    for chunk in chunks:
        lexical = lexical_score(query, chunk.content)
        semantic = cosine_similarity(query_embedding, chunk.embedding_json) if query_embedding and chunk.embedding_json else 0.0
        score = (lexical * 0.55) + (semantic * 0.45 if query_embedding and chunk.embedding_json else 0.0)
        if score <= 0:
            continue
        scored.append(
            KnowledgeSnippet(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                title=chunk.document.title,
                content=chunk.content,
                score=score,
            )
        )
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:top_k]
