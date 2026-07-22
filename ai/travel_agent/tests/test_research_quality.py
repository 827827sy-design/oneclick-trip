from __future__ import annotations

import json
import subprocess

from app.domain.models import ToolDataMode, ToolResult
from app.tools.research import (
    AgentReachResearchCoordinator,
    AgentReachWebFetch,
    AgentReachWebSearch,
    ResearchQualityPipeline,
    ResearchResultCache,
)


def test_quality_pipeline_prioritizes_official_and_extracts_corroborated_claims() -> None:
    result = ToolResult(
        success=True,
        source="agent-reach/exa",
        data_mode=ToolDataMode.REALTIME,
        data={
            "items": [
                {
                    "title": "游客攻略",
                    "url": "https://www.xiaohongshu.com/explore/1",
                    "summary": "全程约50公里，通常需要2-3天完成。",
                    "platform": "xiaohongshu",
                },
                {
                    "title": "景区官网",
                    "url": "https://www.ems517.com/route",
                    "summary": "全程50-60公里，需要2至3天完成，累计爬升2600米。",
                    "platform": "web",
                },
                {
                    "title": "政府公告",
                    "url": "https://www.emeishan.gov.cn/notice",
                    "summary": "登山路线全程约52公里，建议2天完成。",
                    "platform": "web",
                },
            ]
        },
    )

    enriched = ResearchQualityPipeline(official_domains=["ems517.com"]).enrich(result)

    assert enriched.data["items"][0]["source_tier"] == "official"
    assert enriched.data["quality"]["official_source_count"] == 2
    assert enriched.data["quality"]["official_source_missing"] is False
    assert any(
        claim["metric"] == "duration" and claim["corroborated"]
        for claim in enriched.data["evidence_claims"]
    )
    assert enriched.confidence > 0.7


def test_search_cache_avoids_second_upstream_call() -> None:
    calls = []
    payload = {
        "results": [
            {"title": "路线", "url": "https://example.com/route", "text": "详情"}
        ]
    }

    def runner(args, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    search = AgentReachWebSearch(
        executable="python",
        runner=runner,
        cache=ResearchResultCache(ttl_seconds=60),
    )
    first = search.search("峨眉山路线")
    second = search.search("峨眉山路线")

    assert first.data_mode is ToolDataMode.REALTIME
    assert second.data_mode is ToolDataMode.CACHE
    assert second.data["cache_hit"] is True
    assert len(calls) == 1


def test_web_fetch_normalizes_mcporter_content() -> None:
    payload = {
        "content": [
            {
                "type": "text",
                "text": "# 峨眉山旅游网\nURL: https://www.ems517.com/route\n\n官方路线正文",
            }
        ]
    }

    def runner(args, timeout):
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    result = AgentReachWebFetch(executable="python", runner=runner).fetch(
        ["https://www.ems517.com/route"]
    )

    assert result.success is True
    assert result.data["pages"][0]["title"] == "峨眉山旅游网"
    assert "官方路线正文" in result.data["pages"][0]["content"]


def test_web_fetch_reports_partial_result_and_uses_cache() -> None:
    calls = []
    payload = {
        "content": [
            {
                "type": "text",
                "text": "# 景区公告\nURL: https://www.ems517.com/notice\n\n公告正文",
            }
        ]
    }

    def runner(args, timeout):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    fetcher = AgentReachWebFetch(
        executable="python",
        runner=runner,
        cache=ResearchResultCache(ttl_seconds=60),
    )
    urls = [
        "https://www.ems517.com/notice",
        "https://www.ems517.com/route",
    ]
    first = fetcher.fetch(urls)
    second = fetcher.fetch(urls)

    assert first.data["partial"] is True
    assert first.data["missing_urls"] == ["https://www.ems517.com/route"]
    assert second.data_mode is ToolDataMode.CACHE
    assert len(calls) == 1


def test_quality_pipeline_does_not_treat_destination_altitude_as_ascent() -> None:
    result = ToolResult(
        success=True,
        source="agent-reach/exa",
        data_mode=ToolDataMode.REALTIME,
        data={
            "items": [
                {
                    "title": "徒步记录",
                    "url": "https://example.com/hike",
                    "summary": "海拔从500米爬升至3079米，累计爬升约2600米。",
                    "platform": "web",
                }
            ]
        },
    )

    enriched = ResearchQualityPipeline().enrich(result)
    ascent_claims = [
        claim
        for claim in enriched.data["evidence_claims"]
        if claim["metric"] == "ascent"
    ]

    assert len(ascent_claims) == 1
    assert ascent_claims[0]["lower"] == 2600


def test_coordinator_recovers_official_sources_and_tracks_attempts() -> None:
    class FakeSearch:
        def search(self, query: str, *, limit: int = 5) -> ToolResult:
            if query.startswith("site:ems517.com"):
                items = [
                    {
                        "title": "官方安全公告",
                        "url": "https://www.ems517.com/notice",
                        "summary": "夜间禁止徒步登山。",
                        "platform": "web",
                    }
                ]
            else:
                items = [
                    {
                        "title": "游客记录",
                        "url": "https://example.com/guide",
                        "summary": "通常需要2天完成。",
                        "platform": "web",
                    }
                ]
            return ToolResult(
                success=True,
                source="fake-search",
                data_mode=ToolDataMode.REALTIME,
                data={"query": query, "count": len(items), "items": items},
            )

    result = AgentReachResearchCoordinator(FakeSearch()).research(
        "峨眉山徒步安全规则",
        official_domains=["ems517.com"],
        limit=5,
    )

    assert result.success is True
    assert result.data["quality"]["official_source_missing"] is False
    assert result.data["items"][0]["source_tier"] == "official"
    assert len(result.data["search_attempts"]) == 2


def test_coordinator_merges_full_page_content_by_canonical_url() -> None:
    class FakeSearch:
        def search(self, query: str, *, limit: int = 5) -> ToolResult:
            del query, limit
            return ToolResult(
                success=True,
                source="fake-search",
                data_mode=ToolDataMode.REALTIME,
                data={
                    "items": [
                        {
                            "title": "峨眉山完整攻略",
                            "url": "https://example.com/guide?utm_source=search",
                            "summary": "这是搜索摘要。",
                            "platform": "web",
                        },
                        {
                            "title": "抓取失败的资料",
                            "url": "https://example.com/missing",
                            "summary": "保留这段摘要。",
                            "platform": "web",
                        },
                    ]
                },
            )

    class FakeFetcher:
        def fetch(self, urls: list[str]) -> ToolResult:
            assert len(urls) == 2
            return ToolResult(
                success=True,
                source="fake-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={
                    "pages": [
                        {
                            "title": "峨眉山完整攻略",
                            "url": "https://example.com/guide",
                            "content": "完整正文" * 1000,
                        }
                    ]
                },
            )

    result = AgentReachResearchCoordinator(FakeSearch(), FakeFetcher()).research(
        "峨眉山攻略",
        limit=2,
        fetch_top=2,
    )

    assert len(result.data["items"][0]["content"]) == 4000
    assert result.data["items"][0]["content_source"] == "full_page"
    assert result.data["items"][1]["content"] == "保留这段摘要。"
    assert result.data["items"][1]["content_source"] == "search_summary"


def test_web_fetch_rejects_private_network_urls() -> None:
    result = AgentReachWebFetch(executable="python").fetch(["http://127.0.0.1/admin"])

    assert result.success is False
    assert result.error_code == "RESEARCH_FETCH_PRIVATE_URL"
