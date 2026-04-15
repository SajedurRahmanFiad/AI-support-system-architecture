from __future__ import annotations

import math

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
