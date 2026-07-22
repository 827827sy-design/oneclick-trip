from __future__ import annotations

import hashlib
import re

from app.knowledge_pipeline.models import CleanedKnowledgeRecord
from app.vectorstore import KnowledgeDocument


class KnowledgeChunker:
    def __init__(self, max_chars: int = 500, overlap_chars: int = 60) -> None:
        self._max_chars = max_chars
        self._overlap_chars = overlap_chars

    def build_documents(
        self,
        batch_id: str,
        records: list[CleanedKnowledgeRecord],
    ) -> list[KnowledgeDocument]:
        documents = []
        for record in records:
            chunks = self._split(record.content)
            for index, chunk in enumerate(chunks):
                identity = hashlib.sha256(
                    f"{record.record_id}|{index}|{chunk}".encode("utf-8")
                ).hexdigest()[:20]
                documents.append(
                    KnowledgeDocument(
                        document_id=f"{record.record_id}-{identity}",
                        text=f"{record.title}\n{chunk}",
                        knowledge_base=record.knowledge_base,
                        city=record.city,
                        category=record.category,
                        source=record.source,
                        updated_at=record.updated_at,
                        metadata={
                            "batch_id": batch_id,
                            "record_id": record.record_id,
                            "chunk_index": index,
                            "chunk_count": len(chunks),
                            "source_tier": record.source_tier,
                            "content_source": record.content_source,
                            "source_url": record.source_url or "",
                            "quality_score": record.quality_score,
                            "city_consistency": record.city_consistency,
                            "detected_cities": "|".join(record.detected_cities),
                            "tags": "|".join(record.tags),
                        },
                    )
                )
        return documents

    def _split(self, text: str) -> list[str]:
        if len(text) <= self._max_chars:
            return [text]
        sentences = [part.strip() for part in re.split(r"(?<=[。！？；!?;])", text) if part.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= self._max_chars:
                current += sentence
                continue
            if current:
                chunks.append(current)
                current = current[-self._overlap_chars :] + sentence
            else:
                chunks.extend(
                    sentence[index : index + self._max_chars]
                    for index in range(0, len(sentence), self._max_chars - self._overlap_chars)
                )
                current = ""
        if current:
            chunks.append(current)
        return chunks or [text]
