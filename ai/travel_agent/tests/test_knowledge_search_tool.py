from pathlib import Path
from uuid import uuid4

from langchain_core.messages import HumanMessage

from app.agents.research_agent import LangChainPhase1ResearchAgent
from app.domain.models import (
    Phase1Research,
    POICandidate,
    ToolDataMode,
    ToolName,
    ToolResult,
    TravelEntities,
    UserPreferences,
)
from app.graph.builder import build_travel_graph
from app.tools.contracts import ToolContext
from app.tools.knowledge import HybridKnowledgeSearchTool
from app.tools.mock_tools import weather_tool
from app.tools.registry import ToolRegistry
from app.vectorstore import ChromaTravelKnowledgeBase, KnowledgeDocument, KnowledgeHit


def build_store() -> ChromaTravelKnowledgeBase:
    path = Path(__file__).resolve().parents[1] / ".data" / f"test-rag-{uuid4().hex}"
    store = ChromaTravelKnowledgeBase(path, collection_prefix="rag_test")
    store.upsert(
        [
            KnowledgeDocument(
                document_id="guide-emei-cableway",
                text="峨眉山雷洞坪到接引殿需要步行，之后可乘金顶索道，具体票价以景区公告为准。",
                knowledge_base="guide",
                city="峨眉山",
                category="攻略",
                source="峨眉山官网",
                metadata={
                    "source_url": "https://example.com/emei",
                    "source_tier": "official",
                    "quality_score": 0.95,
                },
            )
        ]
    )
    return store


def test_hybrid_knowledge_tool_returns_grounded_ranked_hits() -> None:
    result = HybridKnowledgeSearchTool(build_store())(
        ToolContext(
            query="雷洞坪到金顶索道怎么走",
            entities=TravelEntities(destination="峨眉山"),
        )
    )

    assert result.success is True
    assert result.source == "chroma-hybrid-bm25-rerank"
    assert result.data["retrieval_mode"] == "vector_bm25_quality_rerank"
    assert result.data["hits"][0]["source_url"] == "https://example.com/emei"
    assert result.data["hits"][0]["lexical_score"] >= 0


def test_hybrid_search_rejects_a_document_with_incorrect_city_metadata() -> None:
    store = ChromaTravelKnowledgeBase(
        Path(__file__).resolve().parents[1] / ".data" / f"test-rag-{uuid4().hex}",
        collection_prefix="rag_city_recovery",
    )
    store.upsert(
        [
            KnowledgeDocument(
                document_id="xinjiang-wrong-city",
                text="新疆北疆线路可安排喀纳斯、禾木和赛里木湖。",
                knowledge_base="poi",
                city="成都",
                category="景点",
                source="reviewed-web",
                metadata={"source_url": "https://example.com/xinjiang"},
            )
        ]
    )
    tool = HybridKnowledgeSearchTool(store)

    xinjiang = tool(
        ToolContext(
            query="新疆有哪些景点",
            entities=TravelEntities(destination="新疆北疆"),
        )
    )
    chengdu = tool(
        ToolContext(
            query="成都有哪些景点",
            entities=TravelEntities(destination="成都"),
        )
    )

    assert xinjiang.success is False
    assert chengdu.success is False


def test_hybrid_search_recovers_normalized_city_alias_metadata() -> None:
    store = ChromaTravelKnowledgeBase(
        Path(__file__).resolve().parents[1] / ".data" / f"test-rag-{uuid4().hex}",
        collection_prefix="rag_city_alias_recovery",
    )
    store.upsert(
        [
            KnowledgeDocument(
                document_id="chengdu-city-alias",
                text="成都武侯祠适合了解三国历史文化。",
                knowledge_base="poi",
                city="成都市",
                category="景点",
                source="reviewed-web",
                metadata={"city_consistency": "MATCH"},
            )
        ]
    )

    result = HybridKnowledgeSearchTool(store)(
        ToolContext(
            query="成都有哪些历史文化景点",
            entities=TravelEntities(destination="成都"),
        )
    )

    assert result.success is True
    assert result.data["hits"][0]["city"] == "成都市"
    assert result.data["hits"][0]["metadata_city_mismatch"] is False


def test_hybrid_search_rejects_low_score_incidental_destination_mentions() -> None:
    class LowScoreKnowledgeBase:
        def hybrid_search(self, *args, **kwargs):
            return [
                KnowledgeHit(
                    document_id="xinjiang-page-with-city-list",
                    text="新疆旅游攻略。热门城市：北京、上海、成都。",
                    distance=1,
                    metadata={"city": "成都", "source": "web"},
                    semantic_score=0,
                    lexical_score=1,
                    rerank_score=0.442,
                )
            ]

    result = HybridKnowledgeSearchTool(LowScoreKnowledgeBase())(
        ToolContext(
            query="成都两日游",
            entities=TravelEntities(destination="成都"),
        )
    )

    assert result.success is False
    assert result.error_code == "KNOWLEDGE_NO_MATCH"


def test_phase1_normalization_preserves_knowledge_provenance() -> None:
    research = Phase1Research(
        destination="新疆",
        weather_summary="晴",
        poi_candidates=[
            POICandidate(
                poi_id="model-id",
                name="喀纳斯",
                area="阿勒泰",
                suggested_duration_minutes=240,
            )
        ],
    )
    context = {
        "hits": [
            {
                "document_id": "kb-xinjiang-1",
                "text": "新疆北疆的喀纳斯适合安排一整天游览。",
                "source": "新疆文旅资料",
                "source_url": "https://example.com/kanas",
                "source_tier": "official",
                "rerank_score": 0.92,
            }
        ]
    }

    normalized = LangChainPhase1ResearchAgent._normalize(
        research,
        entities=TravelEntities(destination="新疆"),
        preferences=UserPreferences(),
        weather_summary="晴",
        research_context=context,
    )

    assert normalized.data_mode == "RAG_HYBRID"
    assert normalized.poi_candidates[0].poi_id == "KB-POI-1"
    assert normalized.poi_candidates[0].source_document_ids == ["kb-xinjiang-1"]
    assert normalized.poi_candidates[0].source_urls == ["https://example.com/kanas"]
    assert normalized.research_sources[0].url == "https://example.com/kanas"


def knowledge_result() -> ToolResult:
    return ToolResult(
        success=True,
        source="chroma-hybrid-bm25-rerank",
        data_mode=ToolDataMode.CACHE,
        data={
            "retrieval_mode": "vector_bm25_quality_rerank",
            "hits": [
                {
                    "text": "峨眉山金顶可观云海，出行前需要核对天气与景区公告。",
                    "source": "峨眉山官网",
                    "source_url": "https://example.com/emei",
                    "rerank_score": 0.9,
                }
            ],
        },
    )


def test_general_qa_uses_reviewed_knowledge_without_agent_reach() -> None:
    calls = 0

    def knowledge_tool(_: ToolContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return knowledge_result()

    graph = build_travel_graph(
        tool_registry=ToolRegistry({ToolName.KNOWLEDGE_SEARCH: knowledge_tool})
    )
    result = graph.invoke(
        {
            "conversation_id": "rag-query",
            "user_id": "rag-user",
            "messages": [HumanMessage(content="峨眉山金顶有什么值得看的？")],
        }
    )

    assert calls == 1
    assert result["selected_tools"] == ["knowledge_search"]
    assert "峨眉山金顶可观云海" in result["messages"][-1].content
    assert ToolName.TRAVEL_RESEARCH.value not in result["tool_results"]


def test_planning_passes_knowledge_result_into_phase1_tool_state() -> None:
    def knowledge_tool(_: ToolContext) -> ToolResult:
        return knowledge_result()

    result = build_travel_graph(
        tool_registry=ToolRegistry(
            {
                ToolName.WEATHER: weather_tool,
                ToolName.KNOWLEDGE_SEARCH: knowledge_tool,
            }
        )
    ).invoke(
        {
            "conversation_id": "rag-plan",
            "user_id": "rag-user",
            "messages": [
                HumanMessage(content="帮我规划峨眉山三日游，两个人，总预算5000")
            ],
        }
    )

    assert result["selected_tools"] == ["weather", "knowledge_search"]
    assert result["tool_results"]["knowledge_search"].success is True
