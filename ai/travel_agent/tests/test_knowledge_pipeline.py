import asyncio
from pathlib import Path
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.knowledge_pipeline import (
    KnowledgeBatchStatus,
    KnowledgeBatchDecisionRequest,
    KnowledgePipelineService,
    KnowledgeRecordDeleteRequest,
    KnowledgeRecordReviewRequest,
    KnowledgeRecordReviewStatus,
    JsonKnowledgeBatchRepository,
    PandasKnowledgeCleaner,
    RawKnowledgeRecord,
)
from app.main import create_app
from app.memory.checkpoints import InMemoryCheckpointBackend
from app.vectorstore import ChromaTravelKnowledgeBase, KnowledgeDocument


def sample_records() -> list[RawKnowledgeRecord]:
    return [
        RawKnowledgeRecord(
            title="  成都大熊猫繁育研究基地  ",
            content="熊猫基地适合上午参观，建议预留三到四小时，并提前核对预约要求。",
            city="成都市",
            category="景区",
            source="official-site",
            source_url="HTTPS://PANDA.EXAMPLE/guide/?utm_source=test",
            source_tier="official",
            tags=["亲子", "自然", "亲子"],
        ),
        RawKnowledgeRecord(
            title="熊猫基地旧摘要",
            content="同一个链接的较短内容，用于验证 URL 去重逻辑。",
            city="成都",
            category="景点",
            source="community",
            source_url="https://panda.example/guide",
            source_tier="community",
        ),
        RawKnowledgeRecord(
            title="内容不完整",
            content="太短",
            city="",
            category="景点",
        ),
        RawKnowledgeRecord(
            title="成都火锅",
            content="成都火锅常见牛油锅底，热门时段建议错峰，并根据个人口味选择辣度。",
            city="成都",
            category="餐饮",
            source="editor",
            source_tier="trusted",
            tags=["火锅", "本地美食"],
        ),
    ]


def build_service() -> tuple[KnowledgePipelineService, ChromaTravelKnowledgeBase]:
    path = Path(__file__).resolve().parents[1] / ".data" / f"test-pipeline-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(path, collection_prefix="pipeline_test")
    return KnowledgePipelineService(store), store


def test_pandas_cleaner_normalizes_deduplicates_and_reports_quality() -> None:
    cleaned, rejected, report = PandasKnowledgeCleaner().clean(sample_records())

    assert [item.knowledge_base for item in cleaned] == ["poi", "food"]
    assert cleaned[0].city == "成都"
    assert cleaned[0].source_url == "https://panda.example/guide"
    assert cleaned[0].tags == ["亲子", "自然"]
    assert report.input_count == 4
    assert report.cleaned_count == 2
    assert report.rejected_count == 2
    assert report.duplicate_count == 1
    assert report.knowledge_base_counts == {"poi": 1, "food": 1}
    assert {reason for item in rejected for reason in item.reasons} >= {
        "DUPLICATE_RECORD",
        "CONTENT_TOO_SHORT",
        "CITY_MISSING",
    }


def test_cleaner_rejects_unknown_category_instead_of_crashing_on_nan() -> None:
    cleaned, rejected, report = PandasKnowledgeCleaner().clean(
        [
            RawKnowledgeRecord(
                title="Unsupported category sample",
                content="This record is long enough to reach category validation safely.",
                city="TestCity",
                category="unsupported-category",
                knowledge_base="poi",
            )
        ]
    )

    assert cleaned == []
    assert rejected[0].reasons == ["CATEGORY_UNSUPPORTED"]
    assert report.rejection_reason_counts == {"CATEGORY_UNSUPPORTED": 1}


def test_cleaner_rejects_obvious_city_and_content_mismatch() -> None:
    cleaned, rejected, report = PandasKnowledgeCleaner().clean(
        [
            RawKnowledgeRecord(
                title="新疆旅游终极攻略",
                content=(
                    "新疆旅行可分为北疆和南疆，乌鲁木齐是常见出发点。"
                    "喀纳斯、禾木和赛里木湖适合秋季游览。"
                ),
                city="成都",
                category="景点",
                source_url="https://example.com/xinjiang",
            )
        ]
    )

    assert cleaned == []
    assert rejected[0].reasons == ["CITY_CONTENT_MISMATCH"]
    assert rejected[0].city == "成都"
    assert "新疆" in rejected[0].detected_cities
    assert report.rejection_reason_counts["CITY_CONTENT_MISMATCH"] == 1


def test_cleaner_keeps_balanced_cross_city_comparison() -> None:
    cleaned, rejected, _ = PandasKnowledgeCleaner().clean(
        [
            RawKnowledgeRecord(
                title="成都和重庆周末游怎么选",
                content=(
                    "成都适合美食和历史文化体验，重庆适合山城夜景。"
                    "成都与重庆各有特点，可以按出行偏好选择。"
                ),
                city="成都",
                category="攻略",
            )
        ]
    )

    assert rejected == []
    assert cleaned[0].city_consistency == "MATCH"
    assert cleaned[0].detected_cities[:2] == ["成都", "重庆"]


def test_publish_chunks_cleaned_records_into_isolated_chroma_collections() -> None:
    service, store = build_service()
    batch = service.preview(sample_records())

    published = service.publish(batch.batch_id)

    assert batch.status is KnowledgeBatchStatus.PREVIEWED
    assert published.status is KnowledgeBatchStatus.PUBLISHED
    assert published.published_document_count == 2
    assert store.count("poi") == 1
    assert store.count("food") == 1
    hit = store.search("poi", "熊猫基地上午参观", city="成都")[0]
    assert hit.metadata["batch_id"] == batch.batch_id
    assert hit.metadata["source_tier"] == "official"
    assert hit.metadata["quality_score"] > 0.8


def test_rebuild_index_removes_stale_chunks_and_restores_approved_records() -> None:
    service, store = build_service()
    batch = service.preview(sample_records())
    published = service.publish(batch.batch_id, reviewer="admin")
    store.upsert(
        [
            KnowledgeDocument(
                document_id="stale-chengdu-document",
                text="这是一条不在审核仓库中的历史残留向量。",
                knowledge_base="poi",
                city="成都",
                category="景点",
                source="stale-test",
            )
        ]
    )

    result = service.rebuild_index()

    assert result.removed_document_count == published.published_document_count + 1
    assert result.rebuilt_document_count == published.published_document_count
    assert result.published_batch_count == 1
    assert store.count("poi") == 1
    assert store.count("food") == 1
    assert store.search("poi", "历史残留", city="成都")[0].document_id != "stale-chengdu-document"


def test_manual_rejection_is_persisted_and_excluded_from_publish() -> None:
    service, store = build_service()
    batch = service.preview(sample_records())
    rejected_record = batch.records[0]

    reviewed = service.review_record(
        batch.batch_id,
        rejected_record.record_id,
        KnowledgeRecordReviewRequest(
            status=KnowledgeRecordReviewStatus.REJECTED,
            reviewer="admin",
            reason="开放时间来源已经过期",
            note="等待官网更新后重新采集",
        ),
    )
    published = service.publish(batch.batch_id, reviewer="admin")

    assert reviewed.manual_rejected_count == 1
    assert reviewed.records[0].reviewed_by == "admin"
    assert reviewed.records[0].review_reason == "开放时间来源已经过期"
    assert published.status is KnowledgeBatchStatus.PUBLISHED
    assert published.manual_rejected_count == 1
    assert published.approved_review_count == 1
    assert store.count("poi") == 0
    assert store.count("food") == 1


def test_approved_record_deletion_removes_published_chunks_and_keeps_audit() -> None:
    service, store = build_service()
    batch = service.preview(sample_records())
    published = service.publish(batch.batch_id, reviewer="admin")
    record = next(item for item in published.records if item.knowledge_base == "poi")

    deleted = service.delete_approved_record(
        batch.batch_id,
        record.record_id,
        KnowledgeRecordDeleteRequest(
            reviewer="admin",
            reason="官网已确认该资料失效",
        ),
    )

    assert all(item.record_id != record.record_id for item in deleted.records)
    assert deleted.deleted_record_count == 1
    assert deleted.deleted_records[0].deleted_by == "admin"
    assert deleted.deleted_records[0].reason == "官网已确认该资料失效"
    assert deleted.deleted_records[0].removed_document_count == 1
    assert deleted.published_document_count == 1
    assert store.count("poi") == 0
    assert store.count("food") == 1


def test_only_approved_records_can_be_deleted() -> None:
    service, _ = build_service()
    batch = service.preview(sample_records())

    try:
        service.delete_approved_record(
            batch.batch_id,
            batch.records[0].record_id,
            KnowledgeRecordDeleteRequest(reviewer="admin", reason="测试删除"),
        )
    except ValueError as exc:
        assert str(exc) == "只有已通过的资料可以删除"
    else:
        raise AssertionError("pending record deletion should fail")


def test_record_can_be_restored_and_rejected_batch_can_be_reopened() -> None:
    service, _ = build_service()
    batch = service.preview(sample_records())
    record_id = batch.records[0].record_id
    service.review_record(
        batch.batch_id,
        record_id,
        KnowledgeRecordReviewRequest(
            status=KnowledgeRecordReviewStatus.REJECTED,
            reviewer="admin",
            reason="需要复核",
        ),
    )

    restored = service.review_record(
        batch.batch_id,
        record_id,
        KnowledgeRecordReviewRequest(
            status=KnowledgeRecordReviewStatus.PENDING,
            reviewer="admin",
        ),
    )
    rejected = service.reject_batch(
        batch.batch_id,
        KnowledgeBatchDecisionRequest(
            reviewer="admin",
            reason="本批次来源整体不可靠",
        ),
    )
    reopened = service.reopen_batch(batch.batch_id, "admin")

    assert restored.records[0].review_status is KnowledgeRecordReviewStatus.PENDING
    assert restored.records[0].review_reason is None
    assert rejected.status is KnowledgeBatchStatus.REJECTED
    assert rejected.rejection_reason == "本批次来源整体不可靠"
    assert reopened.status is KnowledgeBatchStatus.PREVIEWED
    assert reopened.rejection_reason is None


def test_json_repository_keeps_review_batch_across_service_instances() -> None:
    path = Path(__file__).resolve().parents[1] / ".data" / f"test-repository-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(path / "chroma", collection_prefix="persistent_test")
    repository_path = path / "knowledge_batches.json"
    first = KnowledgePipelineService(
        store,
        repository=JsonKnowledgeBatchRepository(repository_path),
    )
    batch = first.preview(sample_records())

    second = KnowledgePipelineService(
        store,
        repository=JsonKnowledgeBatchRepository(repository_path),
    )

    assert second.get(batch.batch_id).report.cleaned_count == 2
    assert second.list()[0].batch_id == batch.batch_id


def test_internal_knowledge_api_previews_and_publishes_batch() -> None:
    service, _ = build_service()
    application = create_app(
        InMemoryCheckpointBackend(),
        knowledge_pipeline_service=service,
    )

    async def flow():
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            preview = await client.post(
                "/v1/internal/knowledge/batches/preview",
                json={"records": [item.model_dump(mode="json") for item in sample_records()]},
            )
            batch_id = preview.json()["batch_id"]
            publish = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/publish"
            )
            stats = await client.get("/v1/internal/knowledge/stats")
            batches = await client.get("/v1/internal/knowledge/batches")
            return preview, publish, stats, batches

    preview, publish, stats, batches = asyncio.run(flow())

    assert preview.status_code == 200
    assert preview.json()["report"]["duplicate_count"] == 1
    assert publish.status_code == 200
    assert publish.json()["status"] == "PUBLISHED"
    assert stats.json()["total_documents"] == 2
    assert len(batches.json()["batches"]) == 1


def test_internal_review_api_rejects_restores_and_filters_publish() -> None:
    service, _ = build_service()
    application = create_app(
        InMemoryCheckpointBackend(),
        knowledge_pipeline_service=service,
    )

    async def flow():
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            preview = await client.post(
                "/v1/internal/knowledge/batches/preview",
                json={"records": [item.model_dump(mode="json") for item in sample_records()]},
            )
            batch = preview.json()
            batch_id = batch["batch_id"]
            record_id = batch["records"][0]["record_id"]
            rejected_record = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/records/{record_id}/review",
                json={
                    "status": "REJECTED",
                    "reviewer": "admin",
                    "reason": "来源时间过旧",
                },
            )
            rejected_batch = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/reject",
                json={"reviewer": "admin", "reason": "整批复核"},
            )
            reopened = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/reopen",
                json={"reviewer": "admin"},
            )
            published = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/publish",
                json={"reviewer": "admin"},
            )
            return rejected_record, rejected_batch, reopened, published

    rejected_record, rejected_batch, reopened, published = asyncio.run(flow())

    assert rejected_record.status_code == 200
    assert rejected_record.json()["manual_rejected_count"] == 1
    assert rejected_batch.json()["status"] == "REJECTED"
    assert reopened.json()["status"] == "PREVIEWED"
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["manual_rejected_count"] == 1
    assert published.json()["approved_review_count"] == 1


def test_internal_api_deletes_an_approved_record() -> None:
    service, store = build_service()
    application = create_app(
        InMemoryCheckpointBackend(),
        knowledge_pipeline_service=service,
    )

    async def flow():
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            preview = await client.post(
                "/v1/internal/knowledge/batches/preview",
                json={"records": [item.model_dump(mode="json") for item in sample_records()]},
            )
            batch_id = preview.json()["batch_id"]
            published = await client.post(
                f"/v1/internal/knowledge/batches/{batch_id}/publish",
                json={"reviewer": "admin"},
            )
            record_id = published.json()["records"][0]["record_id"]
            deleted = await client.request(
                "DELETE",
                f"/v1/internal/knowledge/batches/{batch_id}/records/{record_id}",
                json={"reviewer": "admin", "reason": "来源内容已经过期"},
            )
            stats = await client.get("/v1/internal/knowledge/stats")
            return deleted, stats

    deleted, stats = asyncio.run(flow())

    assert deleted.status_code == 200
    assert deleted.json()["deleted_record_count"] == 1
    assert deleted.json()["deleted_records"][0]["reason"] == "来源内容已经过期"
    assert stats.json()["total_documents"] == 1
    assert store.count("poi") == 0
