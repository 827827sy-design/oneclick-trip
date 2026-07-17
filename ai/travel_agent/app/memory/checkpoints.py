from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import time
from typing import Any, Iterator, Protocol, Sequence
from urllib.parse import quote

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from redis import Redis

from app.domain import models as domain_models


class CheckpointBackend(Protocol):
    def create(self) -> BaseCheckpointSaver:
        """Create a LangGraph-compatible checkpoint saver."""


class InMemoryCheckpointBackend:
    """Development and tests only; process restarts discard all checkpoints."""

    def create(self) -> BaseCheckpointSaver:
        return InMemorySaver()


class PlainRedisSaver(BaseCheckpointSaver):
    """LangGraph saver for ordinary Redis 6+, without Redis Stack modules."""

    def __init__(self, redis_url: str, *, ttl_minutes: int = 120) -> None:
        allowed_types = [
            (value.__module__, value.__name__)
            for value in vars(domain_models).values()
            if isinstance(value, type) and value.__module__ == domain_models.__name__
        ]
        super().__init__(
            serde=JsonPlusSerializer(allowed_msgpack_modules=allowed_types)
        )
        self._redis = Redis.from_url(redis_url, decode_responses=False)
        self._ttl_seconds = max(ttl_minutes, 1) * 60
        self._root = "oneclick:langgraph"

    def ping(self) -> bool:
        return bool(self._redis.ping())

    def close(self) -> None:
        self._redis.close()

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config["configurable"]["thread_id"])
        namespace = str(config["configurable"].get("checkpoint_ns", ""))
        base = self._base(thread_id, namespace)
        checkpoint_id = get_checkpoint_id(config)
        if not checkpoint_id:
            latest = self._redis.zrevrange(f"{base}:ids", 0, 0)
            if not latest:
                return None
            checkpoint_id = latest[0].decode()
        record = self._redis.hgetall(f"{base}:checkpoint:{checkpoint_id}")
        if not record:
            return None
        checkpoint = self.serde.loads_typed(
            (record[b"checkpoint_type"].decode(), record[b"checkpoint_data"])
        )
        metadata = self.serde.loads_typed(
            (record[b"metadata_type"].decode(), record[b"metadata_data"])
        )
        parent_id = record.get(b"parent_id", b"").decode() or None
        writes = []
        raw_writes = self._redis.hgetall(f"{base}:writes:{checkpoint_id}")
        for _, payload in sorted(raw_writes.items()):
            task_id, channel, value, _task_path = self.serde.loads_typed(self._unpack(payload))
            writes.append((task_id, channel, value))
        resolved_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }
        parent_config = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": parent_id,
                }
            }
            if parent_id
            else None
        )
        return CheckpointTuple(
            config=resolved_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=writes,
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if config is None:
            thread_ids = [value.decode() for value in self._redis.smembers(f"{self._root}:threads")]
            namespaces_by_thread = {
                thread_id: [
                    value.decode()
                    for value in self._redis.smembers(self._namespace_set_key(thread_id))
                ]
                for thread_id in thread_ids
            }
        else:
            thread_id = str(config["configurable"]["thread_id"])
            namespace = str(config["configurable"].get("checkpoint_ns", ""))
            namespaces_by_thread = {thread_id: [namespace]}

        emitted = 0
        before_id = get_checkpoint_id(before) if before else None
        for thread_id, namespaces in namespaces_by_thread.items():
            for namespace in namespaces:
                base = self._base(thread_id, namespace)
                for raw_id in self._redis.zrevrange(f"{base}:ids", 0, -1):
                    checkpoint_id = raw_id.decode()
                    if before_id and checkpoint_id >= before_id:
                        continue
                    item = self.get_tuple(
                        {
                            "configurable": {
                                "thread_id": thread_id,
                                "checkpoint_ns": namespace,
                                "checkpoint_id": checkpoint_id,
                            }
                        }
                    )
                    if item is None:
                        continue
                    if filter and not all(item.metadata.get(key) == value for key, value in filter.items()):
                        continue
                    yield item
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del new_versions
        thread_id = str(config["configurable"]["thread_id"])
        namespace = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = checkpoint["id"]
        parent_id = config["configurable"].get("checkpoint_id") or ""
        base = self._base(thread_id, namespace)
        checkpoint_type, checkpoint_data = self.serde.dumps_typed(checkpoint)
        metadata_type, metadata_data = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )
        record_key = f"{base}:checkpoint:{checkpoint_id}"
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.hset(
            record_key,
            mapping={
                "checkpoint_type": checkpoint_type,
                "checkpoint_data": checkpoint_data,
                "metadata_type": metadata_type,
                "metadata_data": metadata_data,
                "parent_id": parent_id,
            },
        )
        pipeline.zadd(f"{base}:ids", {checkpoint_id: time()})
        pipeline.sadd(f"{self._root}:threads", thread_id)
        pipeline.sadd(self._namespace_set_key(thread_id), namespace)
        for key in (record_key, f"{base}:ids", self._namespace_set_key(thread_id)):
            pipeline.expire(key, self._ttl_seconds)
        pipeline.execute()
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        namespace = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])
        key = f"{self._base(thread_id, namespace)}:writes:{checkpoint_id}"
        pipeline = self._redis.pipeline(transaction=True)
        for index, (channel, value) in enumerate(writes):
            write_index = WRITES_IDX_MAP.get(channel, index)
            field = f"{task_id}:{write_index}"
            payload = self._pack(self.serde.dumps_typed((task_id, channel, value, task_path)))
            if write_index >= 0:
                pipeline.hsetnx(key, field, payload)
            else:
                pipeline.hset(key, field, payload)
        pipeline.expire(key, self._ttl_seconds)
        pipeline.execute()

    def delete_thread(self, thread_id: str) -> None:
        pattern = f"{self._root}:{quote(thread_id, safe='')}:*"
        keys = list(self._redis.scan_iter(match=pattern))
        if keys:
            self._redis.delete(*keys)
        self._redis.srem(f"{self._root}:threads", thread_id)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ):
        items = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for item in items:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    def _base(self, thread_id: str, namespace: str) -> str:
        return f"{self._root}:{quote(thread_id, safe='')}:{quote(namespace, safe='')}"

    def _namespace_set_key(self, thread_id: str) -> str:
        return f"{self._root}:{quote(thread_id, safe='')}:namespaces"

    @staticmethod
    def _pack(value: tuple[str, bytes]) -> bytes:
        type_name, payload = value
        return type_name.encode() + b"\0" + payload

    @staticmethod
    def _unpack(value: bytes) -> tuple[str, bytes]:
        type_name, payload = value.split(b"\0", 1)
        return type_name.decode(), payload


class PlainRedisCheckpointBackend:
    def __init__(self, url: str, *, ttl_minutes: int = 120) -> None:
        self._saver = PlainRedisSaver(url, ttl_minutes=ttl_minutes)

    def create(self) -> BaseCheckpointSaver:
        return self._saver

    def ping(self) -> bool:
        return self._saver.ping()

    def close(self) -> None:
        self._saver.close()


@dataclass(frozen=True, slots=True)
class RedisCheckpointSettings:
    url: str
    ttl_minutes: int = 120
    refresh_on_read: bool = True

    def as_ttl_config(self) -> dict[str, int | bool]:
        return {
            "default_ttl": self.ttl_minutes,
            "refresh_on_read": self.refresh_on_read,
        }
