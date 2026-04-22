from __future__ import annotations

import math
from typing import Any
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services.llm.factory import build_llm_provider
from app.services.llm.base import AttachmentInsight


class ProductRecognizer:
    def __init__(self, db: Session, brand_id: int) -> None:
        self.db = db
        self.brand_id = brand_id
        self.provider = build_llm_provider()

    def add_product_image(
        self,
        product_name: str,
        category: str,
        storage_path: str,
        mime_type: str,
        image_data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> models.ProductImage:
        metadata_dict = dict(metadata or {})
        insight, _warning = self._safe_analyze_attachment("image", mime_type, image_data)
        fingerprint_text = self._build_reference_fingerprint(
            product_name=product_name,
            category=category,
            summary=insight.summary,
            extracted_text=insight.extracted_text,
            metadata=metadata_dict,
        )
        image_embedding, _embedding_warning = self._safe_embed_image(image_data)
        if not image_embedding:
            fallback_embeddings = self._safe_embed_texts([fingerprint_text])
            image_embedding = fallback_embeddings[0] if fallback_embeddings else None

        metadata_dict.update(
            {
                "visual_summary": insight.summary,
                "visible_text": insight.extracted_text,
                "fingerprint_text": fingerprint_text,
                "mime_type": mime_type,
            }
        )

        product_img = models.ProductImage(
            brand_id=self.brand_id,
            product_name=product_name,
            product_category=category,
            storage_path=storage_path,
            image_embedding=image_embedding,
            product_metadata=metadata_dict,
        )
        self.db.add(product_img)
        self.db.commit()
        self.db.refresh(product_img)
        return product_img

    def recognize_product_from_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        customer_text: str = "",
    ) -> dict[str, Any]:
        warnings: list[str] = []
        query_insight, insight_warning = self._safe_analyze_attachment("image", mime_type, image_data)
        if insight_warning:
            warnings.append(insight_warning)

        query_text = self._build_lookup_text(
            summary=query_insight.summary,
            extracted_text=query_insight.extracted_text,
            customer_text=customer_text,
        )
        query_embedding, embedding_warning = self._safe_embed_image(image_data)
        if embedding_warning:
            warnings.append(embedding_warning)

        if not query_embedding:
            query_embeddings = self._safe_embed_texts([query_text]) if query_text else []
            query_embedding = query_embeddings[0] if query_embeddings else None

        product_images = list(
            self.db.scalars(
                select(models.ProductImage)
                .where(models.ProductImage.brand_id == self.brand_id)
                .where(models.ProductImage.image_embedding.isnot(None))
            )
        )
        if not product_images:
            return {"matched": False, "error": "No product images trained for this brand"}

        scored_candidates: list[dict[str, Any]] = []
        for product_img in product_images:
            metadata = product_img.product_metadata or {}
            fingerprint_text = metadata.get("fingerprint_text") or self._build_reference_fingerprint(
                product_name=product_img.product_name,
                category=product_img.product_category,
                summary=metadata.get("visual_summary", ""),
                extracted_text=metadata.get("visible_text"),
                metadata=metadata,
            )
            lexical = self._lexical_score(query_text, fingerprint_text)
            semantic = self._cosine_similarity(query_embedding, product_img.image_embedding or [])
            coarse_score = (semantic * 0.75) + (lexical * 0.25)
            scored_candidates.append(
                {
                    "candidate_id": product_img.id,
                    "product_name": product_img.product_name,
                    "category": product_img.product_category,
                    "metadata": metadata,
                    "storage_path": product_img.storage_path,
                    "coarse_score": coarse_score,
                    "visual_summary": metadata.get("visual_summary"),
                    "fingerprint_text": fingerprint_text,
                }
            )

        scored_candidates.sort(key=lambda item: item["coarse_score"], reverse=True)
        top_candidates = scored_candidates[:5]
        reranked, rerank_warning = self._safe_match_product_candidates(mime_type, image_data, self._serialize_candidates(top_candidates))
        if rerank_warning:
            warnings.append(rerank_warning)

        chosen = top_candidates[0] if top_candidates else None
        final_confidence = chosen["coarse_score"] if chosen else 0.0
        explanation = "Matched by visual fingerprint search."

        if reranked and reranked.get("matched") and reranked.get("matched_candidate_id") is not None:
            reranked_choice = next(
                (item for item in top_candidates if item["candidate_id"] == reranked["matched_candidate_id"]),
                None,
            )
            if reranked_choice:
                chosen = reranked_choice
                final_confidence = max(final_confidence, float(reranked.get("confidence", final_confidence)))
                explanation = reranked.get("explanation") or explanation
        elif reranked and reranked.get("matched") is False:
            chosen = None
            final_confidence = float(reranked.get("confidence", 0.0))
            explanation = reranked.get("explanation") or "No confident visual match was found."

        confidence_threshold = 0.58 if self.provider.provider_name == "gemini" else 0.45
        if chosen and final_confidence >= confidence_threshold:
            response = {
                "matched": True,
                "product_name": chosen["product_name"],
                "category": chosen["category"],
                "metadata": chosen["metadata"] or {},
                "confidence": final_confidence,
                "product_image_id": chosen["candidate_id"],
                "visual_summary": query_insight.summary,
                "visible_text": query_insight.extracted_text,
                "explanation": explanation,
                "top_candidates": self._serialize_candidates(top_candidates),
            }
            if warnings:
                response["warning"] = " ".join(dict.fromkeys(warnings))
            return response

        response = {
            "matched": False,
            "confidence": final_confidence,
            "best_guess": chosen["product_name"] if chosen else None,
            "visual_summary": query_insight.summary,
            "visible_text": query_insight.extracted_text,
            "top_candidates": self._serialize_candidates(top_candidates),
            "explanation": explanation,
        }
        if warnings:
            response["warning"] = " ".join(dict.fromkeys(warnings))
        return response

    def get_product_images(self) -> list[dict[str, Any]]:
        product_images = list(
            self.db.scalars(
                select(models.ProductImage)
                .where(models.ProductImage.brand_id == self.brand_id)
                .order_by(models.ProductImage.created_at.desc())
            )
        )
        return [
            {
                "id": img.id,
                "product_name": img.product_name,
                "category": img.product_category,
                "storage_path": img.storage_path,
                "metadata": img.product_metadata or {},
                "created_at": img.created_at,
            }
            for img in product_images
        ]

    def delete_product_image(self, product_image_id: int) -> bool:
        product_img = self.db.get(models.ProductImage, product_image_id)
        if not product_img or product_img.brand_id != self.brand_id:
            return False
        storage_path = Path(product_img.storage_path)
        if not storage_path.is_absolute():
            storage_path = get_settings().upload_path / storage_path
        if storage_path.exists():
            storage_path.unlink(missing_ok=True)
        self.db.delete(product_img)
        self.db.commit()
        return True

    def _build_reference_fingerprint(
        self,
        product_name: str,
        category: str,
        summary: str,
        extracted_text: str | None,
        metadata: dict[str, Any],
    ) -> str:
        aliases = metadata.get("aliases") or []
        alias_text = ", ".join(str(item) for item in aliases)
        meta_bits = []
        for key in ("sku", "color", "size", "material", "brand", "model", "variant"):
            value = metadata.get(key)
            if value:
                meta_bits.append(f"{key}: {value}")
        meta_text = "; ".join(meta_bits)
        return " | ".join(
            part
            for part in [
                f"Product name: {product_name}",
                f"Category: {category}",
                f"Aliases: {alias_text}" if alias_text else "",
                f"Visual summary: {summary}",
                f"Visible text: {extracted_text}" if extracted_text else "",
                f"Attributes: {meta_text}" if meta_text else "",
            ]
            if part
        )

    def _build_lookup_text(self, summary: str, extracted_text: str | None, customer_text: str) -> str:
        return " | ".join(
            part
            for part in [
                f"Customer image summary: {summary}",
                f"Visible text: {extracted_text}" if extracted_text else "",
                f"Customer note: {customer_text}" if customer_text else "",
            ]
            if part
        )

    def _serialize_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "candidate_id": item["candidate_id"],
                "product_name": item["product_name"],
                "category": item["category"],
                "coarse_score": round(float(item["coarse_score"]), 4),
                "visual_summary": item.get("visual_summary"),
                "metadata": item.get("metadata") or {},
            }
            for item in candidates
        ]

    @staticmethod
    def _lexical_score(left: str, right: str) -> float:
        left_words = {item.lower().strip(".,!?|:;") for item in left.split() if len(item) > 2}
        right_words = {item.lower().strip(".,!?|:;") for item in right.split() if len(item) > 2}
        if not left_words:
            return 0.0
        return len(left_words & right_words) / len(left_words)

    @staticmethod
    def _cosine_similarity(vec1: list[float] | None, vec2: list[float] | None) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def _safe_analyze_attachment(self, attachment_type: str, mime_type: str, data: bytes) -> tuple[AttachmentInsight, str | None]:
        try:
            return self.provider.analyze_attachment(attachment_type, mime_type, data), None
        except Exception:
            return (
                AttachmentInsight(
                    attachment_id=0,
                    attachment_type=attachment_type,
                    summary="Attachment received. Detailed visual analysis is temporarily unavailable.",
                    extracted_text=None,
                ),
                "Detailed image analysis was temporarily unavailable, so recognition used a fallback match."
            )

    def _safe_embed_image(self, image_data: bytes) -> tuple[list[float], str | None]:
        try:
            return self.provider.embed_image(image_data), None
        except Exception:
            return [], "Image embedding was temporarily unavailable, so recognition used a fallback match."

    def _safe_embed_texts(self, texts: list[str]) -> list[list[float]]:
        try:
            return self.provider.embed_texts(texts)
        except Exception:
            return []

    def _safe_match_product_candidates(
        self,
        mime_type: str,
        data: bytes,
        candidates: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            return self.provider.match_product_candidates(mime_type, data, candidates), None
        except Exception:
            return None, "Visual reranking was temporarily unavailable, so recognition used the base match score only."
