from langchain_core.messages import HumanMessage

from app.agents.memory_agent import RuleBasedMemoryCandidateAgent
from app.domain.models import (
    MemoryExtraction,
    MemoryOperation,
    TravelEntities,
    UserPreferences,
)
from app.graph.nodes.memory_candidate import make_memory_candidate_node


def invoke(query: str, entities: TravelEntities, agent=None):
    node = make_memory_candidate_node(
        agent or RuleBasedMemoryCandidateAgent(),
        repository=None,
    )
    return node.invoke(
        {
            "user_id": "memory-user",
            "messages": [HumanMessage(content=query)],
            "entities": entities,
            "user_preferences": UserPreferences(),
        }
    )


def test_one_off_trip_preference_is_not_saved_as_long_term_memory() -> None:
    patch = invoke(
        "这次成都旅行喜欢美食",
        TravelEntities(explicit_preferences=["美食"]),
    )

    assert patch["memory_updated"] is False
    assert patch["user_preferences"].liked_tags == []


def test_explicit_stable_preference_is_saved() -> None:
    patch = invoke(
        "以后旅行我都喜欢美食",
        TravelEntities(explicit_preferences=["美食"]),
    )

    assert patch["memory_updated"] is True
    assert patch["user_preferences"].liked_tags == ["美食"]
    assert patch["user_preferences"].memory_items[0].evidence == "以后旅行我都喜欢美食"


class SensitiveMemoryAgent:
    def extract(self, query, entities, preferences):
        del query, entities, preferences
        return MemoryExtraction(
            operations=[
                MemoryOperation(
                    action="upsert",
                    category="tag",
                    key="phone",
                    value="secret",
                    confidence=0.99,
                    evidence="我的手机号是 13800000000",
                    source="explicit",
                )
            ]
        )

    async def aextract(self, query, entities, preferences):
        return self.extract(query, entities, preferences)


def test_sensitive_memory_candidate_is_rejected_by_code_policy() -> None:
    patch = invoke("记住我的手机号", TravelEntities(), SensitiveMemoryAgent())

    assert patch["memory_updated"] is False
    assert patch["memory_operations"] == []
