from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.domain.models import ToolDataMode
from app.tools.research.agent_reach import AgentReachDiagnostics, AgentReachWebSearch


def test_agent_reach_search_normalizes_and_deduplicates_results() -> None:
    payload = {
        "structuredContent": {
            "results": [
                {
                    "title": "峨眉山徒步路线",
                    "url": "https://example.com/emei?utm_source=test",
                    "text": "包含路段和耗时",
                    "score": 0.91,
                },
                {
                    "title": "重复来源",
                    "url": "https://example.com/emei?utm_medium=agent",
                    "text": "不应重复出现",
                },
                {
                    "title": "小红书经验",
                    "url": "https://www.xiaohongshu.com/explore/123",
                    "summary": "游客实际体验",
                },
            ]
        }
    }
    calls = []

    def runner(args, timeout):
        calls.append((args, timeout))
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    result = AgentReachWebSearch(
        executable="python",
        timeout_seconds=12,
        runner=runner,
    ).search("峨眉山 徒步 攻略", limit=5)

    assert result.success is True
    assert result.data_mode is ToolDataMode.REALTIME
    assert result.source == "agent-reach/exa"
    assert result.data["count"] == 2
    assert result.data["items"][1]["platform"] == "xiaohongshu"
    assert result.confidence == 0.91
    assert Path(calls[0][0][0]).stem.lower() == "python"
    assert calls[0][0][1] == "call"
    assert calls[0][0][2] == "exa.web_search_exa"
    assert calls[0][0][3] == "query=峨眉山 徒步 攻略"
    assert calls[0][1] == 12


def test_agent_reach_search_rejects_empty_query_without_running_command() -> None:
    result = AgentReachWebSearch(executable="python").search("   ")

    assert result.success is False
    assert result.error_code == "RESEARCH_QUERY_MISSING"


def test_agent_reach_search_maps_timeout_to_retryable_tool_result() -> None:
    def runner(args, timeout):
        raise subprocess.TimeoutExpired(args, timeout)

    result = AgentReachWebSearch(
        executable="python",
        timeout_seconds=3,
        runner=runner,
    ).search("峨眉山")

    assert result.success is False
    assert result.error_code == "AGENT_REACH_TIMEOUT"
    assert result.retryable is True


def test_agent_reach_doctor_returns_report() -> None:
    def runner(args, timeout):
        return subprocess.CompletedProcess(args, 0, stdout="web: ready", stderr="")

    result = AgentReachDiagnostics(executable="python", runner=runner).check()

    assert result.success is True
    assert result.data["report"] == "web: ready"


def test_agent_reach_search_parses_mcporter_exa_text_blocks() -> None:
    payload = {
        "content": [
            {
                "type": "text",
                "text": (
                    "Title: 峨眉山徒步路线\n"
                    "URL: https://example.com/route\n"
                    "Published: 2026-07-01T00:00:00.000Z\n"
                    "Author: 示例作者\n"
                    "Highlights:\n"
                    "全程约 50 公里，需要 2 至 3 天。\n"
                    "---\n"
                    "Title: 峨眉山补给指南\n"
                    "URL: https://example.com/supply\n"
                    "Published: N/A\n"
                    "Author: N/A\n"
                    "Highlights:\n"
                    "沿途补给点有限。"
                ),
            }
        ]
    }

    def runner(args, timeout):
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    result = AgentReachWebSearch(executable="python", runner=runner).search("峨眉山")

    assert result.success is True
    assert result.data["count"] == 2
    assert result.data["items"][0]["published_at"] == "2026-07-01T00:00:00.000Z"
    assert result.data["items"][1]["published_at"] is None
