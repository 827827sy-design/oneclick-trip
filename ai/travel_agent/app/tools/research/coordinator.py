from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

from app.domain.models import ToolDataMode, ToolResult
from app.tools.research.agent_reach import AgentReachWebFetch, AgentReachWebSearch
from app.tools.research.quality import ResearchQualityPipeline


class AgentReachResearchCoordinator:
    """Combines broad discovery with official-domain recovery before ranking."""

    def __init__(
        self,
        search: AgentReachWebSearch,
        fetcher: AgentReachWebFetch | None = None,
    ) -> None:
        self._search = search
        self._fetcher = fetcher

    def research(
        self,
        query: str,
        *,
        official_domains: list[str] | None = None,
        trusted_domains: list[str] | None = None,
        limit: int = 5,
        fetch_top: int = 0,
    ) -> ToolResult:
        domains = _validated_domains(official_domains or [])
        retrieval_limit = min(max(limit * 2, limit), 10)
        attempts = [(query, self._search.search(query, limit=retrieval_limit))]
        for domain in domains[:3]:
            official_query = f"site:{domain} {query}"
            attempts.append(
                (official_query, self._search.search(official_query, limit=min(limit, 5)))
            )

        successful = [(attempt_query, result) for attempt_query, result in attempts if result.success]
        if not successful:
            result = attempts[0][1]
            data = dict(result.data)
            data["search_attempts"] = _attempt_summaries(attempts)
            return result.model_copy(update={"data": data})

        merged_items = []
        seen_urls = set()
        elapsed_ms = 0
        for _, result in successful:
            elapsed_ms += int(result.data.get("elapsed_ms") or 0)
            for item in result.data.get("items", []):
                url = str(item.get("url") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged_items.append(item)

        merged = ToolResult(
            success=True,
            source="agent-reach/exa-multi-source",
            data_mode=(
                ToolDataMode.CACHE
                if all(result.data_mode is ToolDataMode.CACHE for _, result in successful)
                else ToolDataMode.REALTIME
            ),
            data={
                "query": query,
                "provider": "exa",
                "count": len(merged_items),
                "items": merged_items,
                "elapsed_ms": elapsed_ms,
                "search_attempts": _attempt_summaries(attempts),
            },
        )
        enriched = ResearchQualityPipeline(
            official_domains=domains,
            trusted_domains=trusted_domains or [],
        ).enrich(merged, max_results=limit)
        if not fetch_top or not self._fetcher:
            return enriched

        urls = [
            item["url"]
            for item in enriched.data.get("items", [])[: min(fetch_top, 5)]
        ]
        fetched = self._fetcher.fetch(urls)
        data = dict(enriched.data)
        data["fetch_result"] = fetched.model_dump(mode="json")
        data["items"] = _merge_fetched_content(data.get("items", []), fetched)
        return enriched.model_copy(update={"data": data})


def _validated_domains(domains: list[str]) -> list[str]:
    normalized = []
    for domain in domains:
        value = domain.lower().strip().removeprefix("www.").strip(".")
        if not re.fullmatch(r"[a-z0-9.-]+", value):
            raise ValueError(f"invalid official domain: {domain}")
        if value not in normalized:
            normalized.append(value)
    return normalized


def _attempt_summaries(attempts: list[tuple[str, ToolResult]]) -> list[dict[str, object]]:
    return [
        {
            "query": query,
            "success": result.success,
            "count": result.data.get("count", 0),
            "error_code": result.error_code,
            "elapsed_ms": result.data.get("elapsed_ms"),
        }
        for query, result in attempts
    ]


def _merge_fetched_content(
    items: list[dict[str, object]],
    fetched: ToolResult,
) -> list[dict[str, object]]:
    pages = (
        {
            _canonical_url(str(page.get("url") or "")): page
            for page in fetched.data.get("pages", [])
            if page.get("url") and page.get("content")
        }
        if fetched.success
        else {}
    )
    merged = []
    for item in items:
        next_item = dict(item)
        page = pages.get(_canonical_url(str(item.get("url") or "")))
        if page:
            next_item["content"] = str(page["content"]).strip()
            next_item["content_source"] = "full_page"
            next_item["fetched_title"] = page.get("title")
        else:
            next_item["content"] = str(item.get("summary") or "").strip()
            next_item["content_source"] = "search_summary"
        merged.append(next_item)
    return merged


def _canonical_url(value: str) -> str:
    try:
        parts = urlsplit(value.strip())
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
    except ValueError:
        return value.strip()
