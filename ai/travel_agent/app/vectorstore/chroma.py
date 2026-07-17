from __future__ import annotations

import hashlib
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    document_id: str
    text: str = Field(min_length=1)
    knowledge_base: str
    city: str
    category: str
    source: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeHit(BaseModel):
    document_id: str
    text: str
    distance: float
    metadata: dict[str, Any]


class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Offline deterministic embedding for development, not semantic production use."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(document) for document in input]

    @staticmethod
    def name() -> str:
        return "oneclick_hash_embedding"

    def get_config(self) -> dict[str, Any]:
        return {"dimension": self.dimension}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> HashEmbeddingFunction:
        return HashEmbeddingFunction(dimension=int(config.get("dimension", 384)))

    def _embed(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", "", text.lower())
        tokens = list(normalized)
        tokens.extend(normalized[index : index + 2] for index in range(max(len(normalized) - 1, 0)))
        vector = [0.0] * self.dimension
        for token in tokens or [normalized]:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class ChromaTravelKnowledgeBase:
    """Persistent Chroma adapter with one collection per knowledge base."""

    def __init__(
        self,
        persist_directory: Path,
        *,
        collection_prefix: str = "travel_knowledge",
        embedding_function: EmbeddingFunction[Documents] | None = None,
    ) -> None:
        persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._prefix = self._normalize_name(collection_prefix)
        self._embedding = embedding_function or HashEmbeddingFunction()

    def upsert(self, documents: list[KnowledgeDocument]) -> None:
        grouped: dict[str, list[KnowledgeDocument]] = {}
        for document in documents:
            grouped.setdefault(document.knowledge_base, []).append(document)
        for knowledge_base, items in grouped.items():
            collection = self._collection(knowledge_base)
            collection.upsert(
                ids=[item.document_id for item in items],
                documents=[item.text for item in items],
                metadatas=[self._metadata(item) for item in items],
            )

    def search(
        self,
        knowledge_base: str,
        query: str,
        *,
        city: str | None = None,
        limit: int = 5,
    ) -> list[KnowledgeHit]:
        collection = self._collection(knowledge_base)
        where = {"city": city} if city else None
        result = collection.query(
            query_texts=[query],
            n_results=max(limit, 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        texts = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            KnowledgeHit(
                document_id=document_id,
                text=text or "",
                distance=float(distance),
                metadata=metadata or {},
            )
            for document_id, text, metadata, distance in zip(
                ids,
                texts,
                metadatas,
                distances,
                strict=True,
            )
        ]

    def count(self, knowledge_base: str) -> int:
        return self._collection(knowledge_base).count()

    def seed_demo_documents(self) -> None:
        if self.count("poi") > 0:
            return
        self.upsert(
            [
                KnowledgeDocument(
                    document_id="chengdu-panda-base",
                    text="成都大熊猫繁育研究基地适合上午参观，建议预留三到四小时。",
                    knowledge_base="poi",
                    city="成都",
                    category="景点",
                    source="demo-seed",
                ),
                KnowledgeDocument(
                    document_id="chengdu-kuanzhai",
                    text="宽窄巷子位于成都中心城区，适合城市漫步和体验川西街巷文化。",
                    knowledge_base="poi",
                    city="成都",
                    category="景点",
                    source="demo-seed",
                ),
                KnowledgeDocument(
                    document_id="chengdu-food",
                    text="成都代表美食包括火锅、串串香、担担面和钟水饺。",
                    knowledge_base="food",
                    city="成都",
                    category="美食",
                    source="demo-seed",
                ),
            ]
        )

    def _collection(self, knowledge_base: str):
        suffix = self._normalize_name(knowledge_base)
        return self._client.get_or_create_collection(
            name=f"{self._prefix}_{suffix}",
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self._embedding.name(),
                "embedding_dimension": getattr(self._embedding, "dimension", 0),
            },
            embedding_function=self._embedding,
        )

    def _metadata(self, document: KnowledgeDocument) -> dict[str, str | int | float | bool]:
        return {
            "city": document.city,
            "category": document.category,
            "source": document.source,
            "updated_at": document.updated_at.isoformat(),
            "embedding_model": self._embedding.name(),
            "embedding_version": "1",
            "embedding_dimension": getattr(self._embedding, "dimension", 0),
        }

    @staticmethod
    def _normalize_name(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_-").lower()
        normalized = normalized or "default"
        if len(normalized) < 3:
            normalized = normalized.ljust(3, "x")
        return normalized[:63].rstrip("_-")
