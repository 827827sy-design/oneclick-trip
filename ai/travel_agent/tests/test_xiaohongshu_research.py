from __future__ import annotations

import json
import subprocess

from app.agents.query_presenter import (
    RuleBasedQueryPresenterAgent,
    _presenter_result_payload,
)
from app.domain.models import Intent, ToolDataMode, ToolResult, TravelEntities
from app.tools.contracts import ToolContext
from app.tools.research import ResearchResultCache, XiaohongshuResearchTool


def test_xiaohongshu_search_reads_details_and_normalizes_engagement() -> None:
    calls = []
    search_payload = [
        {
            "rank": 1,
            "author": "徒步者",
            "likes": "1.8万",
            "title": "峨眉山两日徒步记录",
            "url": (
                "https://www.xiaohongshu.com/search_result/abc"
                "?xsec_token=token-value&xsec_source=pc_search"
            ),
            "published_at": "2026-07-18",
        }
    ]
    detail_payload = [
        {"field": "content", "value": "两天累计徒步约12小时。"},
        {"field": "collects", "value": "139"},
        {"field": "comments", "value": "53"},
        {"field": "tags", "value": "#峨眉山, #徒步"},
    ]

    def runner(args, timeout):
        calls.append(args)
        payload = detail_payload if args[2] == "note" else search_payload
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    tool = XiaohongshuResearchTool(
        executable="python",
        runner=runner,
        result_limit=5,
        detail_limit=1,
        detail_delay_seconds=0,
    )
    result = tool(
        ToolContext(
            query="峨眉山徒步攻略",
            entities=TravelEntities(destination="峨眉山"),
        )
    )

    assert result.success is True
    assert result.source == "agent-reach/opencli-xiaohongshu"
    assert result.bookable is False
    assert result.data["count"] == 1
    assert result.data["detail_count"] == 1
    assert result.data["items"][0]["likes"] == 18_000
    assert result.data["items"][0]["summary"] == "两天累计徒步约12小时。"
    assert result.data["items"][0]["url"] == (
        "https://www.xiaohongshu.com/search_result/abc"
    )
    assert "xsec_token=token-value" in calls[1][3]
    assert "xsec_source" not in calls[1][3]
    assert "xsec_token" not in result.model_dump_json()


def test_xiaohongshu_search_uses_ttl_cache() -> None:
    calls = 0
    payload = [
        {
            "rank": 1,
            "author": "作者",
            "likes": "12",
            "title": "成都美食攻略",
            "url": "https://www.xiaohongshu.com/search_result/food?xsec_token=token",
            "published_at": "2026-07-10",
        }
    ]

    def runner(args, timeout):
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    tool = XiaohongshuResearchTool(
        executable="python",
        runner=runner,
        result_limit=3,
        detail_limit=0,
        cache=ResearchResultCache(ttl_seconds=60),
    )
    context = ToolContext(query="成都美食攻略")

    first = tool(context)
    second = tool(context)

    assert first.data_mode is ToolDataMode.REALTIME
    assert second.data_mode is ToolDataMode.CACHE
    assert second.data["cache_hit"] is True
    assert calls == 1


def test_xiaohongshu_auth_failure_is_not_retried_by_adapter() -> None:
    def runner(args, timeout):
        return subprocess.CompletedProcess(
            args,
            1,
            stdout="",
            stderr="AUTH_REQUIRED 请先登录小红书",
        )

    result = XiaohongshuResearchTool(
        executable="python",
        runner=runner,
        detail_limit=0,
    )(ToolContext(query="成都攻略"))

    assert result.success is False
    assert result.error_code == "XIAOHONGSHU_AUTH_REQUIRED"
    assert result.retryable is False
    assert result.data["platform_status"]["searched"] is False


def test_presenter_compacts_research_and_fallback_surfaces_experience() -> None:
    result = ToolResult(
        success=True,
        source="agent-reach/opencli-xiaohongshu",
        data_mode=ToolDataMode.REALTIME,
        data={
            "count": 8,
            "detail_count": 1,
            "items": [
                {
                    "title": "峨眉山徒步实测",
                    "url": "https://www.xiaohongshu.com/search_result/note",
                    "summary": "全程约十小时，补水点较少。" + "路线记录" * 300,
                    "author": "旅行者",
                    "likes": 88,
                    "internal_debug": "must-not-reach-the-model",
                }
            ],
        },
    )

    payload = _presenter_result_payload("xiaohongshu_research", result)
    reply = RuleBasedQueryPresenterAgent().present(
        "峨眉山徒步多久？",
        Intent.GENERAL_QA,
        TravelEntities(destination="峨眉山"),
        {"xiaohongshu_research": result},
    )

    assert len(payload["data"]["items"][0]["summary"]) <= 503
    assert "internal_debug" not in json.dumps(payload)
    assert "全程约十小时" in reply
    assert "小红书已搜索 8 篇，精读 1 篇" in reply
