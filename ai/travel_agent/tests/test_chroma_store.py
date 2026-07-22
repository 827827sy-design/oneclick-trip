from pathlib import Path
from uuid import uuid4

from app.vectorstore import ChromaTravelKnowledgeBase, KnowledgeDocument


def test_chroma_persists_and_isolates_knowledge_bases() -> None:
    test_path = Path(__file__).resolve().parents[1] / ".data" / f"test-chroma-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(test_path, collection_prefix="test_travel")
    store.upsert(
        [
            KnowledgeDocument(
                document_id="poi-panda",
                text="成都熊猫基地适合上午参观",
                knowledge_base="poi",
                city="成都",
                category="景点",
                source="test",
            ),
            KnowledgeDocument(
                document_id="food-hotpot",
                text="成都火锅和串串香很有代表性",
                knowledge_base="food",
                city="成都",
                category="美食",
                source="test",
            ),
        ]
    )

    poi_hits = store.search("poi", "成都熊猫基地", city="成都")

    assert store.count("poi") == 1
    assert store.count("food") == 1
    assert [hit.document_id for hit in poi_hits] == ["poi-panda"]
    assert poi_hits[0].metadata["embedding_model"] == "oneclick_hash_embedding"
    assert poi_hits[0].metadata["embedding_dimension"] == 384


def test_hybrid_search_combines_bm25_vector_and_quality_reranking() -> None:
    test_path = Path(__file__).resolve().parents[1] / ".data" / f"test-hybrid-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(test_path, collection_prefix="hybrid_travel")
    store.upsert(
        [
            KnowledgeDocument(
                document_id="emei-ticket",
                text="峨眉山雷洞坪到接引殿步行后可乘金顶索道，上行票价需要按官方公告核对。",
                knowledge_base="guide",
                city="峨眉山",
                category="攻略",
                source="official",
                metadata={"quality_score": 0.96, "source_tier": "official"},
            ),
            KnowledgeDocument(
                document_id="emei-scenery",
                text="峨眉山金顶适合观看日出、云海，冬季需要注意保暖。",
                knowledge_base="guide",
                city="峨眉山",
                category="攻略",
                source="editor",
                metadata={"quality_score": 0.8, "source_tier": "trusted"},
            ),
            KnowledgeDocument(
                document_id="chengdu-panda",
                text="成都熊猫基地建议上午前往。",
                knowledge_base="guide",
                city="成都",
                category="攻略",
                source="editor",
                metadata={"quality_score": 0.9, "source_tier": "trusted"},
            ),
        ]
    )

    hits = store.hybrid_search(
        "guide",
        "雷洞坪金顶索道票价",
        city="峨眉山",
        limit=2,
    )

    assert [hit.document_id for hit in hits] == ["emei-ticket", "emei-scenery"]
    assert hits[0].retrieval_mode == "hybrid_vector_bm25_rerank"
    assert hits[0].lexical_score > hits[1].lexical_score
    assert hits[0].rerank_score > hits[1].rerank_score


def test_hybrid_search_keeps_exact_topic_first_in_a_tiny_corpus() -> None:
    test_path = Path(__file__).resolve().parents[1] / ".data" / f"test-tiny-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(test_path, collection_prefix="tiny_travel")
    store.upsert(
        [
            KnowledgeDocument(
                document_id="panda",
                text="成都大熊猫基地建议上午前往，熊猫更加活跃。",
                knowledge_base="poi",
                city="成都",
                category="景点",
                source="test",
            ),
            KnowledgeDocument(
                document_id="kuanzhai",
                text="宽窄巷子适合体验成都街巷文化。",
                knowledge_base="poi",
                city="成都",
                category="景点",
                source="test",
            ),
        ]
    )

    hits = store.hybrid_search(
        "poi",
        "成都大熊猫基地什么时候去最好",
        city="成都",
        limit=2,
    )

    assert [hit.document_id for hit in hits] == ["panda", "kuanzhai"]
    assert hits[0].lexical_score > hits[1].lexical_score
