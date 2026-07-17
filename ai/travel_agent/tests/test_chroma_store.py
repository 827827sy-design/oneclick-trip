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
