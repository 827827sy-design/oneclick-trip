from decimal import Decimal

from app.domain.models import BudgetScope, NextAction, ToolResult, TravelEntities
from app.graph.state import build_initial_state, merge_tool_results


def test_initial_state_contains_required_typed_fields() -> None:
    state = build_initial_state("conversation-1", "user-1")

    assert state["conversation_id"] == "conversation-1"
    assert state["user_id"] == "user-1"
    assert isinstance(state["entities"], TravelEntities)
    assert state["effective_preferences"].liked_tags == []
    assert state["next_action"] == NextAction.LOAD_USER_MEMORY
    assert state["checkpoint_version"] == 0


def test_entities_preserve_budget_semantics() -> None:
    entities = TravelEntities(
        destination="成都",
        days=3,
        people=2,
        budget=Decimal("3000"),
        budget_scope=BudgetScope.PER_PERSON,
    )

    assert entities.budget_scope == BudgetScope.PER_PERSON
    assert entities.currency == "CNY"


def test_parallel_tool_result_reducer_merges_by_tool_name() -> None:
    weather = ToolResult(success=True, data={"temperature": 28})
    hotel = ToolResult(success=True, data={"count": 2})

    merged = merge_tool_results({"weather": weather}, {"hotel": hotel})

    assert set(merged) == {"weather", "hotel"}
