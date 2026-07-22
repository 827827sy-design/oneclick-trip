from langchain_core.messages import HumanMessage

from app.agents.memory_agent import RuleBasedMemoryCandidateAgent
from app.domain.models import (
    MemoryExtraction,
    MemoryItem,
    MemoryOperation,
    TravelEntities,
    UserPreferences,
)
from app.graph.nodes.memory_candidate import make_memory_candidate_node
from app.graph.nodes.state_normalizer import sanitize_preferences


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


class OneOffMemoryAgent:
    def extract(self, query, entities, preferences):
        del query, entities, preferences
        return MemoryExtraction(
            operations=[
                MemoryOperation(
                    action="upsert",
                    category="activity",
                    key="preferred_activity",
                    value="峨眉山",
                    confidence=0.99,
                    evidence="这次只去峨眉山",
                    source="explicit",
                ),
                MemoryOperation(
                    action="upsert",
                    category="avoidance",
                    key="avoidance",
                    value="其他景点",
                    confidence=0.99,
                    evidence="这次不要其他景点",
                    source="explicit",
                ),
            ]
        )

    async def aextract(self, query, entities, preferences):
        return self.extract(query, entities, preferences)


def test_one_off_high_confidence_llm_operations_are_still_rejected() -> None:
    patch = invoke(
        "这次只去峨眉山，不要其他景点",
        TravelEntities(),
        OneOffMemoryAgent(),
    )

    assert patch["memory_updated"] is False
    assert patch["memory_operations"] == []


def test_legacy_one_off_memory_is_sanitized() -> None:
    preferences = UserPreferences(
        liked_tags=["美食", "峨眉山"],
        disliked_tags=["其他景点"],
        memory_items=[
            MemoryItem(
                category="activity",
                key="preferred_activity",
                value="峨眉山",
                confidence=0.99,
                evidence="这次只去峨眉山",
            )
        ],
    )

    sanitized = sanitize_preferences(preferences)

    assert sanitized.liked_tags == ["美食"]
    assert sanitized.disliked_tags == []
    assert sanitized.memory_items == []
