from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.models import ToolName, TravelEntities
from app.knowledge_pipeline.chunker import KnowledgeChunker
from app.knowledge_pipeline.cleaner import PandasKnowledgeCleaner
from app.knowledge_pipeline.models import (
    DeletedKnowledgeRecord,
    KnowledgeBatch,
    KnowledgeBatchDecisionRequest,
    KnowledgeBatchStatus,
    KnowledgeCollectRequest,
    KnowledgeRebuildResult,
    KnowledgeStats,
    KnowledgeRecordReviewRequest,
    KnowledgeRecordDeleteRequest,
    KnowledgeRecordReviewStatus,
    RawKnowledgeRecord,
)
from app.knowledge_pipeline.repository import (
    InMemoryKnowledgeBatchRepository,
    KnowledgeBatchRepository,
)
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry
from app.vectorstore import ChromaTravelKnowledgeBase


class KnowledgePipelineService:
    def __init__(
        self,
        knowledge_base: ChromaTravelKnowledgeBase,
        *,
        research_registry: ToolRegistry | None = None,
        cleaner: PandasKnowledgeCleaner | None = None,
        chunker: KnowledgeChunker | None = None,
        repository: KnowledgeBatchRepository | None = None,
    ) -> None:
        self._knowledge_base = knowledge_base
        self._research_registry = research_registry or ToolRegistry()
        self._cleaner = cleaner or PandasKnowledgeCleaner()
        self._chunker = chunker or KnowledgeChunker()
        self._repository = repository or InMemoryKnowledgeBatchRepository()

    def preview(self, records: list[RawKnowledgeRecord]) -> KnowledgeBatch:
        cleaned, rejected, report = self._cleaner.clean(records)
        batch = KnowledgeBatch(
            batch_id=f"KB-{uuid4().hex[:12]}",
            status=KnowledgeBatchStatus.PREVIEWED,
            records=cleaned,
            rejected=rejected,
            report=report,
        )
        self._repository.save(batch)
        return batch.model_copy(deep=True)

    def collect(self, request: KnowledgeCollectRequest) -> KnowledgeBatch:
        if ToolName.TRAVEL_RESEARCH not in self._research_registry.names:
            raise RuntimeError("Agent Reach 离线采集器未启用")
        result = self._research_registry.invoke(
            ToolName.TRAVEL_RESEARCH,
            ToolContext(
                query=request.query,
                entities=TravelEntities(destination=request.destination),
            ),
        )
        if not result.success:
            raise RuntimeError(result.data.get("message") or result.error_code or "资料采集失败")
        records = [
            RawKnowledgeRecord(
                title=str(item.get("title") or ""),
                content=str(item.get("content") or item.get("summary") or ""),
                city=request.destination,
                category=request.category,
                knowledge_base=request.knowledge_base,
                source=str(item.get("platform") or result.source),
                source_url=item.get("url"),
                source_tier=str(item.get("source_tier") or "unknown"),
                content_source=str(item.get("content_source") or "search_summary"),
                updated_at=item.get("published_at"),
                tags=item.get("tags") or [],
            )
            for item in result.data.get("items", [])
        ]
        if not records:
            raise RuntimeError("采集结果中没有可清洗的资料")
        return self.preview(records)

    def review_record(
        self,
        batch_id: str,
        record_id: str,
        decision: KnowledgeRecordReviewRequest,
    ) -> KnowledgeBatch:
        batch = self._require_batch(batch_id)
        if batch.status is not KnowledgeBatchStatus.PREVIEWED:
            raise ValueError("只有待审核批次可以修改单条审核结果")
        if (
            decision.status is KnowledgeRecordReviewStatus.REJECTED
            and not (decision.reason or "").strip()
        ):
            raise ValueError("人工拒绝资料时必须填写拒绝原因")
        found = False
        reviewed_at = datetime.now(UTC)
        records = []
        for record in batch.records:
            if record.record_id != record_id:
                records.append(record)
                continue
            found = True
            if decision.status is KnowledgeRecordReviewStatus.PENDING:
                records.append(
                    record.model_copy(
                        update={
                            "review_status": decision.status,
                            "review_reason": None,
                            "review_note": None,
                            "reviewed_by": None,
                            "reviewed_at": None,
                        }
                    )
                )
            else:
                records.append(
                    record.model_copy(
                        update={
                            "review_status": decision.status,
                            "review_reason": (
                                decision.reason.strip() if decision.reason else None
                            ),
                            "review_note": decision.note.strip() if decision.note else None,
                            "reviewed_by": decision.reviewer,
                            "reviewed_at": reviewed_at,
                        }
                    )
                )
        if not found:
            raise KeyError(record_id)
        updated = batch.model_copy(update={"records": records})
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def delete_approved_record(
        self,
        batch_id: str,
        record_id: str,
        decision: KnowledgeRecordDeleteRequest,
    ) -> KnowledgeBatch:
        batch = self._require_batch(batch_id)
        if batch.status is KnowledgeBatchStatus.REJECTED:
            raise ValueError("已驳回批次不能删除资料，请先恢复审核")
        reason = decision.reason.strip()
        if not reason:
            raise ValueError("删除已通过资料时必须填写原因")

        record = next((item for item in batch.records if item.record_id == record_id), None)
        if record is None:
            raise KeyError(record_id)
        if record.review_status is not KnowledgeRecordReviewStatus.APPROVED:
            raise ValueError("只有已通过的资料可以删除")

        removed_document_count = 0
        if batch.status is KnowledgeBatchStatus.PUBLISHED:
            removed_document_count = self._knowledge_base.remove_documents_by_record(
                record.knowledge_base,
                record.record_id,
            )

        deleted_at = datetime.now(UTC)
        deletion = DeletedKnowledgeRecord(
            record_id=record.record_id,
            title=record.title,
            knowledge_base=record.knowledge_base,
            deleted_by=decision.reviewer,
            deleted_at=deleted_at,
            reason=reason,
            removed_document_count=removed_document_count,
        )
        updated = batch.model_copy(
            update={
                "records": [item for item in batch.records if item.record_id != record_id],
                "deleted_records": [*batch.deleted_records, deletion],
                "published_document_count": max(
                    0,
                    batch.published_document_count - removed_document_count,
                ),
                "reviewed_by": decision.reviewer,
                "reviewed_at": deleted_at,
                "review_note": f"删除已通过资料：{record.title}；原因：{reason}",
            }
        )
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def reject_batch(
        self,
        batch_id: str,
        decision: KnowledgeBatchDecisionRequest,
    ) -> KnowledgeBatch:
        batch = self._require_batch(batch_id)
        if batch.status is KnowledgeBatchStatus.PUBLISHED:
            raise ValueError("已发布批次不能驳回")
        if not (decision.reason or "").strip():
            raise ValueError("驳回批次时必须填写原因")
        updated = batch.model_copy(
            update={
                "status": KnowledgeBatchStatus.REJECTED,
                "reviewed_by": decision.reviewer,
                "reviewed_at": datetime.now(UTC),
                "rejection_reason": decision.reason.strip(),
                "review_note": decision.note.strip() if decision.note else None,
            }
        )
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def reopen_batch(self, batch_id: str, reviewer: str) -> KnowledgeBatch:
        batch = self._require_batch(batch_id)
        if batch.status is not KnowledgeBatchStatus.REJECTED:
            raise ValueError("只有已驳回批次可以恢复审核")
        updated = batch.model_copy(
            update={
                "status": KnowledgeBatchStatus.PREVIEWED,
                "reviewed_by": reviewer,
                "reviewed_at": datetime.now(UTC),
                "rejection_reason": None,
                "review_note": None,
            }
        )
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def publish(self, batch_id: str, *, reviewer: str = "internal-admin") -> KnowledgeBatch:
        batch = self._require_batch(batch_id)
        if batch.status is KnowledgeBatchStatus.PUBLISHED:
            return batch.model_copy(deep=True)
        if batch.status is KnowledgeBatchStatus.REJECTED:
            raise ValueError("已驳回批次不能发布，请先恢复审核")
        now = datetime.now(UTC)
        approved_records = [
            item.model_copy(
                update={
                    "review_status": KnowledgeRecordReviewStatus.APPROVED,
                    "reviewed_by": item.reviewed_by or reviewer,
                    "reviewed_at": item.reviewed_at or now,
                }
            )
            for item in batch.records
            if item.review_status is not KnowledgeRecordReviewStatus.REJECTED
        ]
        if not approved_records:
            raise ValueError("批次没有人工审核通过的资料，不能发布")
        documents = self._chunker.build_documents(batch.batch_id, approved_records)
        record_by_id = {item.record_id: item for item in approved_records}
        reviewed_records = [record_by_id.get(item.record_id, item) for item in batch.records]
        self._knowledge_base.upsert(documents)
        updated = batch.model_copy(
            update={
                "status": KnowledgeBatchStatus.PUBLISHED,
                "records": reviewed_records,
                "published_at": now,
                "published_document_count": len(documents),
                "reviewed_by": reviewer,
                "reviewed_at": now,
                "rejection_reason": None,
            }
        )
        self._repository.save(updated)
        return updated.model_copy(deep=True)

    def get(self, batch_id: str) -> KnowledgeBatch:
        return self._require_batch(batch_id).model_copy(deep=True)

    def list(self) -> list[KnowledgeBatch]:
        return self._repository.list()

    def stats(self) -> KnowledgeStats:
        bases = {
            name: self._knowledge_base.count(name)
            for name in ("poi", "food", "hotel", "transport", "ticket", "guide")
        }
        batches = self.list()
        return KnowledgeStats(
            total_documents=sum(bases.values()),
            knowledge_bases=bases,
            batch_count=len(batches),
            previewed_batches=sum(item.status is KnowledgeBatchStatus.PREVIEWED for item in batches),
            rejected_batches=sum(item.status is KnowledgeBatchStatus.REJECTED for item in batches),
            published_batches=sum(item.status is KnowledgeBatchStatus.PUBLISHED for item in batches),
        )

    def rebuild_index(self) -> KnowledgeRebuildResult:
        """Recreate Chroma solely from approved records in published audit batches."""
        bases = ("poi", "food", "hotel", "transport", "ticket", "guide")
        removed_count = sum(self._knowledge_base.clear(name) for name in bases)
        published_batches = [
            batch for batch in self.list()
            if batch.status is KnowledgeBatchStatus.PUBLISHED
        ]
        documents = []
        for batch in published_batches:
            approved = [
                record for record in batch.records
                if record.review_status is KnowledgeRecordReviewStatus.APPROVED
            ]
            documents.extend(self._chunker.build_documents(batch.batch_id, approved))
        if documents:
            self._knowledge_base.upsert(documents)
        return KnowledgeRebuildResult(
            removed_document_count=removed_count,
            rebuilt_document_count=len(documents),
            published_batch_count=len(published_batches),
        )

    def _require_batch(self, batch_id: str) -> KnowledgeBatch:
        batch = self._repository.get(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        return batch
