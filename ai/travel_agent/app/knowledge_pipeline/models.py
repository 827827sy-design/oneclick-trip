from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pydantic import BaseModel, Field, computed_field


class KnowledgeBatchStatus(StrEnum):
    PREVIEWED = "PREVIEWED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class KnowledgeRecordReviewStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RawKnowledgeRecord(BaseModel):
    title: str = ""
    content: str = ""
    city: str = ""
    category: str = ""
    knowledge_base: str | None = None
    source: str = "manual"
    source_url: str | None = None
    source_tier: str = "unknown"
    content_source: str = "manual"
    updated_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    price_text: str | None = None
    opening_hours: str | None = None


class CleanedKnowledgeRecord(BaseModel):
    record_id: str
    title: str
    content: str
    city: str
    category: str
    knowledge_base: str
    source: str
    source_url: str | None = None
    source_tier: str
    content_source: str = "manual"
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    price_text: str | None = None
    opening_hours: str | None = None
    quality_score: float = Field(ge=0, le=1)
    fingerprint: str
    city_consistency: str = "UNKNOWN"
    detected_cities: list[str] = Field(default_factory=list)
    review_status: KnowledgeRecordReviewStatus = KnowledgeRecordReviewStatus.PENDING
    review_reason: str | None = None
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class RejectedKnowledgeRecord(BaseModel):
    row_index: int
    title: str = ""
    reasons: list[str]
    city: str = ""
    detected_cities: list[str] = Field(default_factory=list)


class DeletedKnowledgeRecord(BaseModel):
    record_id: str
    title: str
    knowledge_base: str
    deleted_by: str
    deleted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str
    removed_document_count: int = 0


class KnowledgeQualityReport(BaseModel):
    input_count: int
    cleaned_count: int
    rejected_count: int
    duplicate_count: int
    completeness_rate: float = Field(ge=0, le=1)
    official_source_rate: float = Field(ge=0, le=1)
    average_quality_score: float = Field(ge=0, le=1)
    knowledge_base_counts: dict[str, int] = Field(default_factory=dict)
    rejection_reason_counts: dict[str, int] = Field(default_factory=dict)


class KnowledgeBatch(BaseModel):
    batch_id: str
    status: KnowledgeBatchStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    published_at: datetime | None = None
    records: list[CleanedKnowledgeRecord]
    rejected: list[RejectedKnowledgeRecord]
    deleted_records: list[DeletedKnowledgeRecord] = Field(default_factory=list)
    report: KnowledgeQualityReport
    published_document_count: int = 0
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    review_note: str | None = None

    @computed_field
    @property
    def pending_review_count(self) -> int:
        return sum(
            item.review_status is KnowledgeRecordReviewStatus.PENDING
            for item in self.records
        )

    @computed_field
    @property
    def approved_review_count(self) -> int:
        return sum(
            item.review_status is KnowledgeRecordReviewStatus.APPROVED
            for item in self.records
        )

    @computed_field
    @property
    def manual_rejected_count(self) -> int:
        return sum(
            item.review_status is KnowledgeRecordReviewStatus.REJECTED
            for item in self.records
        )

    @computed_field
    @property
    def deleted_record_count(self) -> int:
        return len(self.deleted_records)


class KnowledgePreviewRequest(BaseModel):
    records: list[RawKnowledgeRecord] = Field(min_length=1, max_length=500)


class KnowledgeCollectRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    destination: str = Field(min_length=1, max_length=80)
    category: str = "景点"
    knowledge_base: str = "poi"


class KnowledgeRecordReviewRequest(BaseModel):
    status: KnowledgeRecordReviewStatus
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=1000)


class KnowledgeRecordDeleteRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=300)


class KnowledgeBatchDecisionRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    reason: str | None = Field(default=None, max_length=300)
    note: str | None = Field(default=None, max_length=1000)


class KnowledgePublishRequest(BaseModel):
    reviewer: str = Field(default="internal-admin", min_length=1, max_length=80)


class KnowledgeStats(BaseModel):
    total_documents: int
    knowledge_bases: dict[str, int]
    batch_count: int
    previewed_batches: int
    rejected_batches: int
    published_batches: int


class KnowledgeRebuildResult(BaseModel):
    removed_document_count: int
    rebuilt_document_count: int
    published_batch_count: int


class KnowledgeBatchList(BaseModel):
    batches: list[KnowledgeBatch]
