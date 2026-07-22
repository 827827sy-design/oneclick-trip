from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import chromadb
import jieba
import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel, Field
from rank_bm25 import BM25Plus


jieba.setLogLevel(logging.ERROR)


class KnowledgeDocument(BaseModel):
    document_id: str
    text: str = Field(min_length=1)
    knowledge_base: str
    city: str
    category: str
    source: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class KnowledgeHit(BaseModel):
    document_id: str
    text: str
    distance: float
    metadata: dict[str, Any]
    semantic_score: float = 0
    lexical_score: float = 0
    rerank_score: float = 0
    retrieval_mode: str = "vector"


class HashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Offline deterministic embedding for development, not semantic production use."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(document) for document in input]

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query)

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
        server_url: str | None = None,
    ) -> None:
        if server_url:
            parsed = urlparse(server_url)
            if not parsed.hostname:
                raise ValueError("CHROMA_SERVER_URL must include a hostname")
            self._client = chromadb.HttpClient(
                host=parsed.hostname,
                port=parsed.port or (443 if parsed.scheme == "https" else 8000),
                ssl=parsed.scheme == "https",
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
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
            query_embeddings=[self._query_embedding(query)],
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

    def hybrid_search(
        self,
        knowledge_base: str,
        query: str,
        *,
        city: str | None = None,
        limit: int = 5,
        candidate_multiplier: int = 4,
    ) -> list[KnowledgeHit]:
        """Fuse vector and BM25 recall, then rerank using quality metadata."""
        collection = self._collection(knowledge_base)
        where = {"city": city} if city else None
        corpus = collection.get(
            where=where,
            include=["documents", "metadatas"],
        )
        corpus_ids = list(corpus.get("ids") or [])
        if not corpus_ids:
            return []
        corpus_texts = [text or "" for text in (corpus.get("documents") or [])]
        corpus_metadatas = [metadata or {} for metadata in (corpus.get("metadatas") or [])]
        candidate_count = min(
            len(corpus_ids),
            max(limit, limit * max(candidate_multiplier, 1)),
        )

        vector_result = collection.query(
            query_embeddings=[self._query_embedding(query)],
            n_results=candidate_count,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        vector_ids = list(vector_result.get("ids", [[]])[0])
        vector_distances = [float(value) for value in vector_result.get("distances", [[]])[0]]
        semantic_scores = {
            document_id: max(0.0, min(1.0, 1.0 - distance))
            for document_id, distance in zip(vector_ids, vector_distances, strict=True)
        }
        distance_by_id = dict(zip(vector_ids, vector_distances, strict=True))

        tokenized_corpus = [_tokenize(text) for text in corpus_texts]
        query_tokens = _tokenize(query)
        raw_lexical_scores = (
            BM25Plus(tokenized_corpus).get_scores(query_tokens)
            if query_tokens and any(tokenized_corpus)
            else [0.0] * len(corpus_ids)
        )
        normalized_lexical_scores = _normalize_scores(raw_lexical_scores)
        lexical_scores = dict(zip(corpus_ids, normalized_lexical_scores, strict=True))
        lexical_ids = [
            corpus_ids[index]
            for index in sorted(
                range(len(corpus_ids)),
                key=lambda index: raw_lexical_scores[index],
                reverse=True,
            )[:candidate_count]
        ]

        text_by_id = dict(zip(corpus_ids, corpus_texts, strict=True))
        metadata_by_id = dict(zip(corpus_ids, corpus_metadatas, strict=True))
        candidate_ids = list(dict.fromkeys([*vector_ids, *lexical_ids]))
        normalized_query = _normalize_text(query)
        hits = []
        for document_id in candidate_ids:
            metadata = metadata_by_id[document_id]
            semantic = semantic_scores.get(document_id, 0.0)
            lexical = lexical_scores.get(document_id, 0.0)
            quality = _bounded_score(metadata.get("quality_score"), default=0.5)
            authority = _source_authority(str(metadata.get("source_tier") or "unknown"))
            phrase_match = 1.0 if normalized_query in _normalize_text(text_by_id[document_id]) else 0.0
            semantic_guard = 0.08 if semantic >= 0.7 else 0.0
            rerank = (
                0.42 * semantic
                + 0.33 * lexical
                + 0.12 * quality
                + 0.08 * authority
                + 0.05 * phrase_match
                + semantic_guard
            )
            hits.append(
                KnowledgeHit(
                    document_id=document_id,
                    text=text_by_id[document_id],
                    distance=distance_by_id.get(document_id, 1.0),
                    metadata=metadata,
                    semantic_score=round(semantic, 4),
                    lexical_score=round(lexical, 4),
                    rerank_score=round(rerank, 4),
                    retrieval_mode="hybrid_vector_bm25_rerank",
                )
            )
        return sorted(hits, key=lambda item: item.rerank_score, reverse=True)[: max(limit, 1)]

    def count(self, knowledge_base: str) -> int:
        return self._collection(knowledge_base).count()

    def clear(self, knowledge_base: str) -> int:
        """Remove every indexed chunk from one logical knowledge base."""
        collection = self._collection(knowledge_base)
        document_ids = list(collection.get(include=[]).get("ids") or [])
        if document_ids:
            collection.delete(ids=document_ids)
        return len(document_ids)

    def remove_documents_by_source(self, source: str) -> None:
        for knowledge_base in ("poi", "food", "hotel", "transport", "ticket", "guide"):
            collection = self._collection(knowledge_base)
            matching = collection.get(where={"source": source}, include=[])
            document_ids = list(matching.get("ids") or [])
            if document_ids:
                collection.delete(ids=document_ids)

    def remove_documents_by_record(self, knowledge_base: str, record_id: str) -> int:
        collection = self._collection(knowledge_base)
        matching = collection.get(where={"record_id": record_id}, include=[])
        document_ids = list(matching.get("ids") or [])
        if document_ids:
            collection.delete(ids=document_ids)
        return len(document_ids)

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
        metadata: dict[str, str | int | float | bool] = {
            "city": document.city,
            "category": document.category,
            "source": document.source,
            "updated_at": document.updated_at.isoformat(),
            "embedding_model": self._embedding.name(),
            "embedding_version": "1",
            "embedding_dimension": getattr(self._embedding, "dimension", 0),
        }
        metadata.update(document.metadata)
        return metadata

    def _query_embedding(self, query: str) -> list[float]:
        embed_query = getattr(self._embedding, "embed_query", None)
        if callable(embed_query):
            raw_embedding = embed_query(query)
        else:
            raw_embedding = self._embedding([query])[0]
        normalized = np.asarray(raw_embedding, dtype=np.float32)
        if normalized.ndim == 2 and normalized.shape[0] == 1:
            normalized = normalized[0]
        if normalized.ndim != 1:
            raise ValueError(
                f"Query embedding must be one-dimensional, got {normalized.shape}"
            )
        return normalized.tolist()

    @staticmethod
    def _normalize_name(value: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_-").lower()
        normalized = normalized or "default"
        if len(normalized) < 3:
            normalized = normalized.ljust(3, "x")
        return normalized[:63].rstrip("_-")


def _tokenize(text: str) -> list[str]:
    normalized = _normalize_text(text)
    words = [
        token.strip()
        for token in jieba.lcut(normalized, cut_all=False)
        if token.strip() and re.search(r"[\w\u4e00-\u9fff]", token)
    ]
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    bigrams = [chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))]
    return [*words, *bigrams]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").casefold())


def _normalize_scores(values) -> list[float]:
    scores = [float(value) for value in values]
    if not scores:
        return []
    low, high = min(scores), max(scores)
    if math.isclose(low, high):
        return [1.0 if high > 0 else 0.0 for _ in scores]
    return [(value - low) / (high - low) for value in scores]


def _bounded_score(value: object, *, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _source_authority(source_tier: str) -> float:
    return {
        "official": 1.0,
        "trusted": 0.8,
        "commercial": 0.55,
        "community": 0.4,
        "unknown": 0.2,
    }.get(source_tier, 0.2)
