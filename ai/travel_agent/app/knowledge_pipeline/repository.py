from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Protocol

from app.knowledge_pipeline.models import KnowledgeBatch


class KnowledgeBatchRepository(Protocol):
    def save(self, batch: KnowledgeBatch) -> None: ...

    def get(self, batch_id: str) -> KnowledgeBatch | None: ...

    def list(self) -> list[KnowledgeBatch]: ...


class InMemoryKnowledgeBatchRepository:
    def __init__(self) -> None:
        self._batches: dict[str, KnowledgeBatch] = {}
        self._lock = RLock()

    def save(self, batch: KnowledgeBatch) -> None:
        with self._lock:
            self._batches[batch.batch_id] = batch.model_copy(deep=True)

    def get(self, batch_id: str) -> KnowledgeBatch | None:
        with self._lock:
            batch = self._batches.get(batch_id)
            return batch.model_copy(deep=True) if batch else None

    def list(self) -> list[KnowledgeBatch]:
        with self._lock:
            batches = sorted(
                self._batches.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [item.model_copy(deep=True) for item in batches]


class JsonKnowledgeBatchRepository:
    """Small persistent review queue; the interface can later be backed by MySQL."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = RLock()

    def save(self, batch: KnowledgeBatch) -> None:
        with self._lock:
            batches = self._read_all()
            batches[batch.batch_id] = batch
            self._write_all(batches)

    def get(self, batch_id: str) -> KnowledgeBatch | None:
        with self._lock:
            batch = self._read_all().get(batch_id)
            return batch.model_copy(deep=True) if batch else None

    def list(self) -> list[KnowledgeBatch]:
        with self._lock:
            batches = sorted(
                self._read_all().values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [item.model_copy(deep=True) for item in batches]

    def _read_all(self) -> dict[str, KnowledgeBatch]:
        if not self._path.exists():
            return {}
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return {
            item["batch_id"]: KnowledgeBatch.model_validate(item)
            for item in payload.get("batches", [])
        }

    def _write_all(self, batches: dict[str, KnowledgeBatch]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "batches": [
                item.model_dump(mode="json")
                for item in sorted(batches.values(), key=lambda value: value.created_at)
            ]
        }
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._path)
