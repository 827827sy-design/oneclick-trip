from __future__ import annotations

from app.domain.models import ToolDataMode, ToolResult
from app.tools.contracts import ToolContext
from app.vectorstore import ChromaTravelKnowledgeBase, KnowledgeHit


class HybridKnowledgeSearchTool:
    """Read-only RAG retrieval over reviewed Chroma knowledge collections."""

    def __init__(
        self,
        knowledge_base: ChromaTravelKnowledgeBase,
        *,
        limit: int = 6,
        minimum_rerank_score: float = 0.48,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._limit = limit
        self._minimum_rerank_score = minimum_rerank_score

    def __call__(self, context: ToolContext) -> ToolResult:
        query = (context.query or "").strip()
        if not query:
            return ToolResult(
                success=False,
                source="chroma-hybrid",
                data_mode=ToolDataMode.CACHE,
                data={"message": "知识库检索缺少查询内容"},
                error_code="KNOWLEDGE_QUERY_MISSING",
                retryable=False,
            )
        knowledge_bases = _select_knowledge_bases(query)
        hits: list[tuple[str, KnowledgeHit]] = []
        destination = (context.entities.destination or "").strip()
        for name in knowledge_bases:
            exact_hits = self._knowledge_base.hybrid_search(
                name,
                query,
                city=destination or None,
                limit=self._limit,
            )
            exact_hits = [
                hit for hit in exact_hits
                if not destination or _city_compatible(hit, destination)
            ]
            recovered_hits = []
            if destination and not exact_hits:
                recovered_hits = [
                    hit
                    for hit in self._knowledge_base.hybrid_search(
                        name,
                        query,
                        city=None,
                        limit=max(self._limit * 3, 12),
                    )
                    if _city_compatible(hit, destination)
                ][: self._limit]
            hits.extend((name, hit) for hit in [*exact_hits, *recovered_hits])
        ranked = sorted(hits, key=lambda item: item[1].rerank_score, reverse=True)
        unique = []
        seen = set()
        for knowledge_base, hit in ranked:
            if hit.rerank_score < self._minimum_rerank_score:
                continue
            key = (knowledge_base, hit.document_id)
            if key in seen:
                continue
            seen.add(key)
            unique.append(_hit_payload(knowledge_base, hit, destination))
            if len(unique) >= self._limit:
                break
        if not unique:
            return ToolResult(
                success=False,
                source="chroma-hybrid",
                data_mode=ToolDataMode.CACHE,
                data={
                    "message": "知识库中没有找到相关资料",
                    "query": query,
                    "knowledge_bases": knowledge_bases,
                },
                error_code="KNOWLEDGE_NO_MATCH",
                retryable=False,
            )
        return ToolResult(
            success=True,
            source="chroma-hybrid-bm25-rerank",
            data_mode=ToolDataMode.CACHE,
            confidence=round(sum(item["rerank_score"] for item in unique) / len(unique), 3),
            data={
                "query": query,
                "retrieval_mode": "vector_bm25_quality_rerank",
                "knowledge_bases": knowledge_bases,
                "count": len(unique),
                "hits": unique,
            },
            bookable=False,
        )


def _select_knowledge_bases(query: str) -> list[str]:
    lowered = query.casefold()
    selected = []
    rules = (
        ("food", ("美食", "餐厅", "火锅", "小吃", "吃什么")),
        ("hotel", ("酒店", "住宿", "民宿", "青旅", "住哪里")),
        ("transport", ("交通", "高铁", "火车", "飞机", "地铁", "公交", "怎么走")),
        ("ticket", ("门票", "票价", "预约", "购票", "索道")),
        ("poi", ("景点", "景区", "游玩", "徒步", "登山", "哪里值得去")),
    )
    for knowledge_base, keywords in rules:
        if any(keyword in lowered for keyword in keywords):
            selected.append(knowledge_base)
    selected.extend(name for name in ("guide", "poi") if name not in selected)
    return selected[:4]


def _hit_payload(knowledge_base: str, hit: KnowledgeHit, destination: str) -> dict:
    metadata = hit.metadata
    metadata_city = str(metadata.get("city") or "")
    return {
        "document_id": hit.document_id,
        "knowledge_base": knowledge_base,
        "text": hit.text,
        "city": metadata_city or destination,
        "metadata_city": metadata_city,
        "metadata_city_mismatch": bool(
            destination
            and metadata_city
            and not _same_destination(metadata_city, destination)
        ),
        "category": metadata.get("category"),
        "source": metadata.get("source"),
        "source_url": metadata.get("source_url"),
        "source_tier": metadata.get("source_tier"),
        "updated_at": metadata.get("updated_at"),
        "quality_score": metadata.get("quality_score"),
        "semantic_score": hit.semantic_score,
        "lexical_score": hit.lexical_score,
        "rerank_score": hit.rerank_score,
    }


def _city_compatible(hit: KnowledgeHit, destination: str) -> bool:
    metadata_city = str(hit.metadata.get("city") or "").strip()
    if metadata_city and not _same_destination(metadata_city, destination):
        return False
    consistency = str(hit.metadata.get("city_consistency") or "").upper()
    if consistency in {"MATCH", "UNKNOWN"} and metadata_city:
        return True
    return _strongly_mentions_destination(hit.text, destination)


def _same_destination(left: str, right: str) -> bool:
    normalized_left = _normalize_destination(left)
    normalized_right = _normalize_destination(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or (
            min(len(normalized_left), len(normalized_right)) >= 2
            and (
                normalized_left in normalized_right
                or normalized_right in normalized_left
            )
        )
    )


def _normalize_destination(value: str) -> str:
    normalized = "".join(str(value).casefold().split())
    return normalized[:-1] if len(normalized) > 2 and normalized.endswith("市") else normalized


def _strongly_mentions_destination(text: str, destination: str) -> bool:
    normalized_text = "".join(str(text).casefold().split())
    return any(
        normalized_text.startswith(term) or normalized_text.count(term) >= 2
        for term in _destination_terms(destination)
    )


def _destination_terms(destination: str) -> list[str]:
    normalized = "".join(str(destination).casefold().split())
    if not normalized:
        return []
    terms = [normalized]
    if len(normalized) >= 4:
        terms.extend(
            normalized[index : index + 2]
            for index in range(len(normalized) - 1)
        )
    generic_terms = {"地区", "景区", "城区", "市区", "旅游"}
    return list(dict.fromkeys(term for term in terms if term not in generic_terms))
