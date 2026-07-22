from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock

from app.domain.models import ToolDataMode, ToolResult


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    result: ToolResult


class ResearchResultCache:
    """Small process-local TTL cache for the PoC; Redis can replace it later."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = RLock()

    def get(self, key: str) -> ToolResult | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            data = dict(entry.result.data)
            data["cache_hit"] = True
            return entry.result.model_copy(
                deep=True,
                update={"data": data, "data_mode": ToolDataMode.CACHE},
            )
    def set(self, key: str, result: ToolResult) -> None:
        if not result.success:
            return
        with self._lock:
            self._entries[key] = _CacheEntry(
                expires_at=time.monotonic() + self._ttl_seconds,
                result=result.model_copy(deep=True),
            )
