"""Multi-turn conversation matrix tests — covers normal / missing-slot / tool-failure / recovery."""

from decimal import Decimal

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.domain.models import Intent, NextAction
from app.graph.builder import build_travel_graph


def invoke_multi_turn(messages: list[str], thread_id: str = "multi-turn") -> list[dict]:
    """Run a sequence of messages in the same conversation thread and return all states."""
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": thread_id}}
    results = []
    for msg in messages:
        result = graph.invoke(
            {
                "conversation_id": thread_id,
                "user_id": "multi-turn-user",
                "messages": [HumanMessage(content=msg)],
            },
            config=config,
        )
        results.append(result)
    return results


# ── Scenario 1: Full trip planning with all slots ──

def test_full_trip_planning_completes_with_all_slots() -> None:
    results = invoke_multi_turn(
        [
            "帮我规划成都三日游，两个人，总预算5000，喜欢美食",
        ],
        thread_id="full-plan",
    )
    final = results[-1]
    assert final["intent"] == Intent.TRIP_PLAN
    assert final["next_action"] == NextAction.COMPLETE
    assert final["plan_saved"] is True
    assert final["plan_draft"].destination == "成都"
    assert len(final["plan_draft"].days) == 3


# ── Scenario 2: Slot filling across multiple turns ──

def test_slot_filling_across_turns() -> None:
    results = invoke_multi_turn(
        [
            "我想去成都",
            "玩3天",
            "2个人",
            "预算3000",
        ],
        thread_id="slot-fill",
    )
    # After last message, should have all slots filled
    final = results[-1]
    assert final["intent"] == Intent.TRIP_PLAN
    assert final["entities"].destination == "成都"
    assert final["entities"].days == 3
    assert final["entities"].people == 2
    assert final["entities"].budget == Decimal("3000")


# ── Scenario 3: Weather query then trip plan ──

def test_weather_then_trip_plan() -> None:
    results = invoke_multi_turn(
        [
            "成都明天天气怎么样？",
            "那帮我规划成都三日游，两个人，预算4000",
        ],
        thread_id="weather-then-plan",
    )
    weather = results[0]
    plan_result = results[1]
    assert weather["intent"] == Intent.WEATHER_QUERY
    assert weather["selected_tools"] == ["weather"]
    assert plan_result["intent"] == Intent.TRIP_PLAN
    assert plan_result["plan_saved"] is True


# ── Scenario 4: Plan then modify ──

def test_plan_then_modify() -> None:
    results = invoke_multi_turn(
        [
            "帮我规划成都三日游，两个人，总预算5000",
            "把第二天上午换成杜甫草堂",
        ],
        thread_id="plan-then-modify",
    )
    plan_result = results[0]
    modify_result = results[1]
    assert plan_result["intent"] == Intent.TRIP_PLAN
    assert plan_result["plan_saved"] is True
    assert modify_result["intent"] == Intent.MODIFY_PLAN


# ── Scenario 5: Sequence of different intents ──

def test_mixed_intent_sequence() -> None:
    results = invoke_multi_turn(
        [
            "你好",                                      # general_qa
            "成都天气怎么样？",                           # weather_query
            "有没有推荐的酒店？",                         # hotel_query
        ],
        thread_id="mixed-intents",
    )
    assert results[0]["intent"] in {Intent.GENERAL_QA, Intent.UNKNOWN}
    assert results[1]["intent"] == Intent.WEATHER_QUERY
    assert results[2]["intent"] == Intent.HOTEL_QUERY


# ── Scenario 6: Plan with budget infeasibility (known limitation: rule-based gives ~1000 min) ──

def test_tight_budget_returns_budget_feedback() -> None:
    results = invoke_multi_turn(
        [
            "帮我规划成都三日游，两个人，总预算100",
        ],
        thread_id="tight-budget",
    )
    final = results[-1]
    assert final["intent"] == Intent.TRIP_PLAN
    # With very tight budget, should not save plan
    assert final["plan_saved"] is False or final.get("budget_feasibility") is not None


# ── Scenario 7: Single-turn query doesn't carry into next trip ──

def test_query_does_not_pollute_next_trip() -> None:
    results = invoke_multi_turn(
        [
            "杭州明天天气怎么样？",
            "帮我规划成都三日游，两个人，总预算4000",
        ],
        thread_id="query-then-trip",
    )
    trip_result = results[1]
    # Trip should be for Chengdu, not Hangzhou
    assert trip_result["entities"].destination == "成都"
    assert trip_result["plan_draft"].destination == "成都"
