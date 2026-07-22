from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.domain.models import ToolDataMode, ToolResult
from app.tools.contracts import ToolContext
from app.tools.research.cache import ResearchResultCache
from app.tools.research.tool import build_research_query


CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


class XiaohongshuResearchTool:
    """Read-only Xiaohongshu search through Agent Reach's OpenCLI backend."""

    is_realtime_provider = True

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = 45.0,
        result_limit: int = 8,
        detail_limit: int = 2,
        detail_delay_seconds: float = 2.2,
        runner: CommandRunner | None = None,
        cache: ResearchResultCache | None = None,
    ) -> None:
        if not 1 <= result_limit <= 20:
            raise ValueError("result_limit must be between 1 and 20")
        if not 0 <= detail_limit <= min(result_limit, 3):
            raise ValueError("detail_limit must be between 0 and 3")
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._result_limit = result_limit
        self._detail_limit = detail_limit
        self._detail_delay_seconds = max(detail_delay_seconds, 0)
        self._runner = runner or _run_command
        self._cache = cache

    def __call__(self, context: ToolContext) -> ToolResult:
        query = build_research_query(context)
        if not query:
            return _failure(
                "XIAOHONGSHU_QUERY_MISSING",
                "小红书搜索缺少用户问题或目的地",
                retryable=False,
            )
        cache_key = f"xiaohongshu::{query.casefold()}::{self._result_limit}::{self._detail_limit}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                return cached

        executable = _resolve_executable(self._executable)
        if not executable:
            return _failure(
                "XIAOHONGSHU_OPENCLI_NOT_INSTALLED",
                "OpenCLI 未安装，无法搜索小红书",
                retryable=False,
            )

        started = time.monotonic()
        search = self._execute(
            executable,
            [
                "xiaohongshu",
                "search",
                query,
                "--limit",
                str(self._result_limit),
                "-f",
                "json",
            ],
        )
        if isinstance(search, ToolResult):
            return search
        try:
            items = _normalize_search_items(json.loads(search.stdout))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return _failure(
                "XIAOHONGSHU_RESPONSE_INVALID",
                str(exc),
                retryable=False,
            )

        detail_errors: list[dict[str, str]] = []
        detail_count = 0
        for index, item in enumerate(items[: self._detail_limit]):
            if index and self._detail_delay_seconds:
                time.sleep(self._detail_delay_seconds)
            detail = self._execute(
                executable,
                [
                    "xiaohongshu",
                    "note",
                    _note_url(item["url"]),
                    "-f",
                    "json",
                ],
            )
            if isinstance(detail, ToolResult):
                detail_errors.append(
                    {
                        "url": item["url"],
                        "error_code": detail.error_code or "XIAOHONGSHU_DETAIL_FAILED",
                    }
                )
                continue
            try:
                fields = _normalize_detail(json.loads(detail.stdout))
            except (json.JSONDecodeError, TypeError, ValueError):
                detail_errors.append(
                    {
                        "url": item["url"],
                        "error_code": "XIAOHONGSHU_DETAIL_INVALID",
                    }
                )
                continue
            item["summary"] = fields.get("content", item["summary"])
            item["collects"] = _engagement_count(fields.get("collects"))
            item["comments"] = _engagement_count(fields.get("comments"))
            item["tags"] = fields.get("tags", "")
            detail_count += 1

        for item in items:
            item["url"] = _public_note_url(item["url"])

        elapsed_ms = round((time.monotonic() - started) * 1000)
        result = ToolResult(
            success=True,
            source="agent-reach/opencli-xiaohongshu",
            data_mode=ToolDataMode.REALTIME,
            confidence=0.58,
            bookable=False,
            data={
                "query": query,
                "provider": "opencli-xiaohongshu",
                "count": len(items),
                "detail_count": detail_count,
                "items": items,
                "detail_errors": detail_errors,
                "elapsed_ms": elapsed_ms,
                "platform_status": {
                    "platform": "xiaohongshu",
                    "searched": True,
                    "result_count": len(items),
                    "detail_count": detail_count,
                },
                "usage_policy": {
                    "read_only": True,
                    "bookable": False,
                    "community_experience_only": True,
                    "cannot_override_official_safety_rules": True,
                },
            },
        )
        if self._cache:
            self._cache.set(cache_key, result)
        return result

    def _execute(
        self,
        executable: str,
        arguments: list[str],
    ) -> subprocess.CompletedProcess[str] | ToolResult:
        try:
            completed = self._runner(
                [executable, *arguments],
                self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _failure(
                "XIAOHONGSHU_TIMEOUT",
                "小红书搜索超时",
                retryable=True,
            )
        if completed.returncode == 0:
            return completed
        message = (completed.stderr or completed.stdout or "OpenCLI 调用失败").strip()
        auth_required = "AUTH_REQUIRED" in message or "登录" in message
        return _failure(
            "XIAOHONGSHU_AUTH_REQUIRED" if auth_required else "XIAOHONGSHU_SEARCH_FAILED",
            message[:1000],
            retryable=not auth_required,
        )


def _run_command(
    args: Sequence[str], timeout_seconds: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        shell=False,
    )


def _resolve_executable(explicit: str | None) -> str | None:
    if explicit:
        path = Path(explicit)
        return str(path) if path.exists() else shutil.which(explicit)
    return shutil.which("opencli") or shutil.which("opencli.cmd")


def _normalize_search_items(payload) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("小红书搜索结果不是列表")
    items = []
    seen_urls = set()
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not title or not url or url in seen_urls:
            continue
        seen_urls.add(url)
        author = str(raw.get("author") or "").strip()
        likes = _engagement_count(raw.get("likes"))
        items.append(
            {
                "title": title,
                "url": url,
                "summary": f"作者：{author}；点赞：{likes}",
                "platform": "xiaohongshu",
                "published_at": str(raw.get("published_at") or "").strip() or None,
                "author": author,
                "likes": likes,
                "rank": int(raw.get("rank") or len(items) + 1),
                "source_tier": "community",
                "authority_score": 0.46,
            }
        )
    if not items:
        raise ValueError("小红书没有返回有效笔记")
    return items


def _normalize_detail(payload) -> dict[str, str]:
    if not isinstance(payload, list):
        raise ValueError("小红书详情结果不是字段列表")
    return {
        str(item.get("field")): str(item.get("value") or "")
        for item in payload
        if isinstance(item, dict) and item.get("field")
    }


def _engagement_count(value) -> int:
    text = str(value or "0").strip().lower()
    multiplier = 10_000 if text.endswith("万") else 1
    if multiplier > 1:
        text = text[:-1]
    try:
        return max(round(float(text) * multiplier), 0)
    except ValueError:
        return 0


def _note_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "xsec_source"
        ]
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _public_note_url(url: str) -> str:
    """Remove short-lived search credentials before results enter checkpoints."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _failure(error_code: str, message: str, *, retryable: bool) -> ToolResult:
    return ToolResult(
        success=False,
        source="agent-reach/opencli-xiaohongshu",
        data_mode=ToolDataMode.REALTIME,
        data={
            "message": message,
            "platform_status": {
                "platform": "xiaohongshu",
                "searched": False,
                "result_count": 0,
                "detail_count": 0,
            },
        },
        error_code=error_code,
        retryable=retryable,
        bookable=False,
    )
