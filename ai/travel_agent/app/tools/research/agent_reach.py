from __future__ import annotations

import json
import ipaddress
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field

from app.domain.models import DomainModel, ToolDataMode, ToolResult
from app.tools.research.cache import ResearchResultCache


CommandRunner = Callable[[Sequence[str], float], subprocess.CompletedProcess[str]]


class ResearchItem(DomainModel):
    title: str
    url: str
    summary: str = ""
    platform: str = "web"
    published_at: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)


class FetchedPage(DomainModel):
    title: str
    url: str
    content: str


class AgentReachDiagnostics:
    """Checks Agent Reach's selected upstream channels without changing the system."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = 20.0,
        runner: CommandRunner | None = None,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._runner = runner or _run_command

    def check(self) -> ToolResult:
        executable = _resolve_executable(self._executable, "agent-reach")
        if not executable:
            return _missing_tool_result("agent-reach", "AGENT_REACH_NOT_INSTALLED")

        started = time.monotonic()
        try:
            completed = self._runner([executable, "doctor"], self._timeout_seconds)
        except subprocess.TimeoutExpired:
            return _timeout_result("agent-reach doctor", self._timeout_seconds)

        elapsed_ms = round((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            return ToolResult(
                success=False,
                source="agent-reach-doctor",
                data_mode=ToolDataMode.REALTIME,
                data={
                    "message": _error_message(completed),
                    "elapsed_ms": elapsed_ms,
                },
                error_code="AGENT_REACH_DOCTOR_FAILED",
                retryable=False,
            )
        return ToolResult(
            success=True,
            source="agent-reach-doctor",
            data_mode=ToolDataMode.REALTIME,
            confidence=1.0,
            data={"report": completed.stdout.strip(), "elapsed_ms": elapsed_ms},
        )


class AgentReachWebSearch:
    """Calls the Exa backend configured by Agent Reach and normalizes its JSON output."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        runner: CommandRunner | None = None,
        cache: ResearchResultCache | None = None,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._runner = runner or _run_command
        self._cache = cache

    def search(self, query: str, *, limit: int = 5) -> ToolResult:
        normalized_query = query.strip()
        if not normalized_query:
            return ToolResult(
                success=False,
                source="agent-reach/exa",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "搜索关键词不能为空"},
                error_code="RESEARCH_QUERY_MISSING",
                retryable=False,
            )
        if not 1 <= limit <= 10:
            return ToolResult(
                success=False,
                source="agent-reach/exa",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "搜索结果数量必须在 1 到 10 之间"},
                error_code="RESEARCH_LIMIT_INVALID",
                retryable=False,
            )

        cache_key = f"{normalized_query.casefold()}::{limit}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                return cached

        executable = _resolve_executable(self._executable, "mcporter")
        if not executable:
            return _missing_tool_result("mcporter", "AGENT_REACH_SEARCH_NOT_CONFIGURED")

        started = time.monotonic()
        try:
            completed = self._runner(
                [
                    executable,
                    "call",
                    "exa.web_search_exa",
                    f"query={normalized_query}",
                    f"numResults={limit}",
                    "--output",
                    "json",
                ],
                self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _timeout_result("Agent Reach Exa search", self._timeout_seconds)

        elapsed_ms = round((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            return ToolResult(
                success=False,
                source="agent-reach/exa",
                data_mode=ToolDataMode.REALTIME,
                data={
                    "message": _error_message(completed),
                    "query": normalized_query,
                    "elapsed_ms": elapsed_ms,
                },
                error_code="AGENT_REACH_SEARCH_FAILED",
                retryable=True,
            )

        try:
            payload = _load_json_output(completed.stdout)
            items = _normalize_items(payload, limit)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(
                success=False,
                source="agent-reach/exa",
                data_mode=ToolDataMode.REALTIME,
                data={
                    "message": str(exc),
                    "query": normalized_query,
                    "elapsed_ms": elapsed_ms,
                },
                error_code="AGENT_REACH_RESPONSE_INVALID",
                retryable=False,
            )

        result = ToolResult(
            success=True,
            source="agent-reach/exa",
            data_mode=ToolDataMode.REALTIME,
            confidence=_result_confidence(items),
            data={
                "query": normalized_query,
                "provider": "exa",
                "count": len(items),
                "items": [item.model_dump(mode="json") for item in items],
                "elapsed_ms": elapsed_ms,
            },
        )
        if self._cache:
            self._cache.set(cache_key, result)
        return result


class AgentReachWebFetch:
    """Fetches selected search results through Agent Reach's Exa backend."""

    def __init__(
        self,
        executable: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        runner: CommandRunner | None = None,
        cache: ResearchResultCache | None = None,
    ) -> None:
        self._executable = executable
        self._timeout_seconds = timeout_seconds
        self._runner = runner or _run_command
        self._cache = cache

    def fetch(self, urls: list[str], *, max_characters: int = 50_000) -> ToolResult:
        normalized_urls = _validate_fetch_urls(urls)
        if isinstance(normalized_urls, ToolResult):
            return normalized_urls
        if not 200 <= max_characters <= 50_000:
            return ToolResult(
                success=False,
                source="agent-reach/exa-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "max_characters 必须在 200 到 50000 之间"},
                error_code="RESEARCH_FETCH_LIMIT_INVALID",
                retryable=False,
            )
        cache_key = f"{'|'.join(sorted(normalized_urls))}::{max_characters}"
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached:
                return cached
        executable = _resolve_executable(self._executable, "mcporter")
        if not executable:
            return _missing_tool_result("mcporter", "AGENT_REACH_SEARCH_NOT_CONFIGURED")
        arguments = json.dumps(
            {"urls": normalized_urls, "maxCharacters": max_characters},
            ensure_ascii=False,
        )
        started = time.monotonic()
        try:
            completed = self._runner(
                [
                    executable,
                    "call",
                    "exa.web_fetch_exa",
                    "--args",
                    arguments,
                    "--output",
                    "json",
                ],
                self._timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _timeout_result("Agent Reach Exa fetch", self._timeout_seconds)
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if completed.returncode != 0:
            return ToolResult(
                success=False,
                source="agent-reach/exa-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={"message": _error_message(completed), "elapsed_ms": elapsed_ms},
                error_code="AGENT_REACH_FETCH_FAILED",
                retryable=True,
            )
        try:
            payload = _load_json_output(completed.stdout)
            pages = _normalize_fetched_pages(payload, normalized_urls, max_characters)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(
                success=False,
                source="agent-reach/exa-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={"message": str(exc), "elapsed_ms": elapsed_ms},
                error_code="AGENT_REACH_RESPONSE_INVALID",
                retryable=False,
            )
        result = ToolResult(
            success=True,
            source="agent-reach/exa-fetch",
            data_mode=ToolDataMode.REALTIME,
            confidence=0.75,
            data={
                "count": len(pages),
                "pages": [page.model_dump(mode="json") for page in pages],
                "requested_count": len(normalized_urls),
                "missing_urls": [
                    url
                    for url in normalized_urls
                    if _canonical_url(url)
                    not in {_canonical_url(page.url) for page in pages}
                ],
                "partial": len(pages) < len(normalized_urls),
                "elapsed_ms": elapsed_ms,
            },
        )
        if self._cache:
            self._cache.set(cache_key, result)
        return result


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


def _resolve_executable(explicit: str | None, default_name: str) -> str | None:
    if explicit:
        path = Path(explicit)
        return str(path) if path.exists() else shutil.which(explicit)
    resolved = shutil.which(default_name)
    if resolved:
        return resolved
    scripts_directory = Path(sys.executable).resolve().parent
    for suffix in (".exe", ".cmd", ".bat", ""):
        candidate = scripts_directory / f"{default_name}{suffix}"
        if candidate.exists():
            return str(candidate)
    return None


def _missing_tool_result(tool: str, error_code: str) -> ToolResult:
    return ToolResult(
        success=False,
        source="agent-reach",
        data_mode=ToolDataMode.REALTIME,
        data={"message": f"{tool} 尚未安装或不在 PATH 中"},
        error_code=error_code,
        retryable=False,
    )


def _timeout_result(operation: str, timeout_seconds: float) -> ToolResult:
    return ToolResult(
        success=False,
        source="agent-reach",
        data_mode=ToolDataMode.REALTIME,
        data={"message": f"{operation} 超过 {timeout_seconds:g} 秒未返回"},
        error_code="AGENT_REACH_TIMEOUT",
        retryable=True,
    )


def _error_message(completed: subprocess.CompletedProcess[str]) -> str:
    return (completed.stderr or completed.stdout or "上游命令执行失败").strip()[:1000]


def _load_json_output(output: str) -> Any:
    text = output.strip()
    if not text:
        raise ValueError("上游搜索没有返回内容")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not starts:
            raise
        return json.loads(text[min(starts) :])


def _normalize_items(payload: Any, limit: int) -> list[ResearchItem]:
    records = _find_result_records(payload)
    if records is None:
        raise ValueError("无法从 Agent Reach 返回值中找到结构化 results")

    items: list[ResearchItem] = []
    seen_urls: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        url = str(record.get("url") or record.get("link") or "").strip()
        title = str(record.get("title") or record.get("name") or "").strip()
        if not url or not title:
            continue
        canonical_url = _canonical_url(url)
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        raw_score = record.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        if score is not None:
            score = min(max(score, 0.0), 1.0)
        items.append(
            ResearchItem(
                title=title,
                url=url,
                summary=str(
                    record.get("summary")
                    or record.get("text")
                    or record.get("snippet")
                    or ""
                ).strip(),
                platform=_platform_from_url(url),
                published_at=_optional_text(
                    record.get("publishedDate") or record.get("published_at")
                ),
                score=score,
            )
        )
        if len(items) >= limit:
            break
    if not items:
        raise ValueError("Agent Reach 返回了 results，但没有有效的标题和链接")
    return items


def _find_result_records(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None
    results = payload.get("results")
    if isinstance(results, list):
        return results
    for key in ("data", "result", "structuredContent"):
        nested = payload.get(key)
        if isinstance(nested, str):
            try:
                nested = json.loads(nested)
            except json.JSONDecodeError:
                continue
        found = _find_result_records(nested)
        if found is not None:
            return found
    content = payload.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or not isinstance(block.get("text"), str):
                continue
            try:
                nested = json.loads(block["text"])
            except json.JSONDecodeError:
                records = _parse_exa_text(block["text"])
                if records:
                    return records
                continue
            found = _find_result_records(nested)
            if found is not None:
                return found
    return None


def _parse_exa_text(text: str) -> list[dict[str, str]]:
    """Parse mcporter's documented Exa text blocks without guessing missing fields."""
    records: list[dict[str, str]] = []
    for raw_block in text.replace("\r\n", "\n").split("\n---\n"):
        lines = raw_block.strip().splitlines()
        fields: dict[str, str] = {}
        highlights: list[str] = []
        reading_highlights = False
        for line in lines:
            if line.startswith("Title: "):
                fields["title"] = line.removeprefix("Title: ").strip()
                reading_highlights = False
            elif line.startswith("URL: "):
                fields["url"] = line.removeprefix("URL: ").strip()
                reading_highlights = False
            elif line.startswith("Published: "):
                value = line.removeprefix("Published: ").strip()
                if value and value != "N/A":
                    fields["published_at"] = value
                reading_highlights = False
            elif line == "Highlights:":
                reading_highlights = True
            elif reading_highlights:
                highlights.append(line)
        if fields.get("title") and fields.get("url"):
            fields["summary"] = "\n".join(highlights).strip()[:1200]
            records.append(fields)
    return records


def _validate_fetch_urls(urls: list[str]) -> list[str] | ToolResult:
    if not 1 <= len(urls) <= 5:
        return ToolResult(
            success=False,
            source="agent-reach/exa-fetch",
            data_mode=ToolDataMode.REALTIME,
            data={"message": "正文抓取一次必须包含 1 到 5 个 URL"},
            error_code="RESEARCH_FETCH_URLS_INVALID",
            retryable=False,
        )
    normalized = []
    for url in urls:
        parts = urlsplit(url.strip())
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ToolResult(
                success=False,
                source="agent-reach/exa-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={"message": f"不支持的 URL：{url}"},
                error_code="RESEARCH_FETCH_URL_INVALID",
                retryable=False,
            )
        if parts.hostname.lower() == "localhost" or _is_private_ip(parts.hostname):
            return ToolResult(
                success=False,
                source="agent-reach/exa-fetch",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "禁止读取本机或私有网络地址"},
                error_code="RESEARCH_FETCH_PRIVATE_URL",
                retryable=False,
            )
        normalized.append(url.strip())
    return list(dict.fromkeys(normalized))


def _is_private_ip(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


def _normalize_fetched_pages(
    payload: Any,
    requested_urls: list[str],
    max_characters: int,
) -> list[FetchedPage]:
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        raise ValueError("正文抓取结果缺少 content")
    pages = []
    for index, block in enumerate(content):
        if not isinstance(block, dict) or not isinstance(block.get("text"), str):
            continue
        text = block["text"].strip()
        url_match = re.search(r"^URL:\s*(\S+)\s*$", text, re.MULTILINE)
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        url = url_match.group(1) if url_match else requested_urls[min(index, len(requested_urls) - 1)]
        title = title_match.group(1).strip() if title_match else url
        pages.append(FetchedPage(title=title, url=url, content=text[:max_characters]))
    if not pages:
        raise ValueError("正文抓取没有返回可用页面")
    return pages


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.lower().startswith("utm_")
        )
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def _platform_from_url(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if "xiaohongshu.com" in host:
        return "xiaohongshu"
    if "bilibili.com" in host or "b23.tv" in host:
        return "bilibili"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "weixin.qq.com" in host:
        return "wechat"
    return "web"


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _result_confidence(items: list[ResearchItem]) -> float:
    scores = [item.score for item in items if item.score is not None]
    return round(sum(scores) / len(scores), 3) if scores else 0.7
