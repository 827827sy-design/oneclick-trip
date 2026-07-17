from decimal import Decimal

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.intent_agent import RuleBasedIntentAgent
from app.domain.models import (
    Intent,
    NextAction,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)
from app.graph.builder import build_travel_graph
from app.graph.nodes.state_normalizer import normalize_state
from app.graph.router import route_after_supervisor


def invoke(query: str, **state_overrides):
    graph = build_travel_graph()
    state = {
        "conversation_id": "routing-conversation",
        "user_id": "routing-user",
        "messages": [HumanMessage(content=query)],
        **state_overrides,
    }
    return graph.invoke(state)


def current_plan() -> TravelPlan:
    return TravelPlan(plan_id="PLAN-1", version=1, destination="成都")


class ContextLeakingIntentAgent(RuleBasedIntentAgent):
    def classify(self, query: str, *, context=None):
        decision = super().classify(query, context=context)
        if query == "成都两日游":
            entities = decision.entities.model_copy(
                update={"budget": Decimal("500"), "people": 2}
            )
            return decision.model_copy(update={"entities": entities})
        return decision


def test_rule_agent_extracts_transport_direction_in_text_order() -> None:
    decision = RuleBasedIntentAgent().classify("成都到上海怎么去方便？")

    assert decision.intent == Intent.TRANSPORT_QUERY
    assert decision.entities.origin == "成都"
    assert decision.entities.destination == "上海"


def test_rule_agent_extracts_origin_for_explicit_trip_direction() -> None:
    decision = RuleBasedIntentAgent().classify(
        "帮我规划从成都去大理三日游，一个人，总预算500元"
    )

    assert decision.intent == Intent.TRIP_PLAN
    assert decision.entities.origin == "成都"
    assert decision.entities.destination == "大理"


def test_trip_duration_does_not_use_day_number_from_date() -> None:
    decision = RuleBasedIntentAgent().classify(
        "帮我规划2026年8月1日到8月3日去成都的3日游，2个人，总预算6000元"
    )

    assert decision.intent == Intent.TRIP_PLAN
    assert decision.entities.days == 3
    assert decision.entities.start_date.isoformat() == "2026-08-01"
    assert decision.entities.end_date.isoformat() == "2026-08-03"


def test_travel_desire_routes_to_plan_slot_follow_up() -> None:
    result = invoke("我想去新疆")

    assert result["intent"] == Intent.TRIP_PLAN
    assert result["entities"].destination == "新疆"
    assert result["next_action"] == NextAction.ASK_USER
    assert result["missing_fields"] == ["duration", "people", "budget"]
    assert result["messages"][-1].content == "再告诉我旅行天数或出发与返程日期、同行人数、大概预算，我就可以接着帮你规划。"
    assert result["clarification_reply"].title == "新疆已经记下啦"


def test_slot_follow_up_keeps_pending_trip_plan_intent() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "xinjiang-follow-up"}}
    first = graph.invoke(
        {
            "conversation_id": "xinjiang-follow-up",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="我想去新疆")],
        },
        config=config,
    )
    second = graph.invoke(
        {
            "conversation_id": "xinjiang-follow-up",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="玩3天，2个人，总预算6000元")],
        },
        config=config,
    )

    assert first["next_action"] == NextAction.ASK_USER
    assert second["intent"] == Intent.TRIP_PLAN
    assert second["entities"].destination == "新疆"
    assert second["entities"].days == 3
    assert second["next_action"] == NextAction.COMPLETE
    assert second["plan_saved"] is True


def test_new_trip_request_does_not_reuse_completed_plan_budget() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "fresh-trip-slots"}}
    completed = graph.invoke(
        {
            "conversation_id": "fresh-trip-slots",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="帮我规划成都一日游，一个人，总预算500元")],
        },
        config=config,
    )
    fresh_request = graph.invoke(
        {
            "conversation_id": "fresh-trip-slots",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="我想规划一次新的旅行")],
        },
        config=config,
    )
    nearby_request = graph.invoke(
        {
            "conversation_id": "fresh-trip-slots",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="推荐一个离成都近一些的地方，规划三日游")],
        },
        config=config,
    )

    assert completed["plan_saved"] is True
    assert completed["entities"].budget == Decimal("500")
    assert fresh_request["entities"].budget is None
    assert fresh_request["budget_feasibility"] is None
    assert nearby_request["entities"].budget is None
    assert nearby_request["next_action"] is NextAction.ASK_USER
    assert "budget" in nearby_request["missing_fields"]


def test_fresh_trip_opener_clears_stale_budget_adjustment() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "stale-budget-reset"}}
    failed = graph.invoke(
        {
            "conversation_id": "stale-budget-reset",
            "user_id": "routing-user",
            "messages": [
                HumanMessage(content="帮我规划成都三日游，两个人，总预算500元")
            ],
        },
        config=config,
    )
    fresh = graph.invoke(
        {
            "conversation_id": "stale-budget-reset",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="我想出去旅游，推荐一个地方")],
        },
        config=config,
    )

    assert failed["budget_feasibility"] is not None
    assert failed["entities"].budget == Decimal("500")
    assert fresh["entities"].budget is None
    assert fresh["budget_feasibility"] is None


def test_new_trip_shape_after_budget_failure_does_not_reuse_old_budget() -> None:
    graph = build_travel_graph(
        checkpointer=InMemorySaver(),
        intent_agent=ContextLeakingIntentAgent(),
    )
    config = {"configurable": {"thread_id": "stale-budget-new-shape"}}
    failed = graph.invoke(
        {
            "conversation_id": "stale-budget-new-shape",
            "user_id": "routing-user",
            "messages": [
                HumanMessage(content="帮我规划成都三日游，两个人，总预算500元")
            ],
        },
        config=config,
    )
    fresh = graph.invoke(
        {
            "conversation_id": "stale-budget-new-shape",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="成都两日游")],
        },
        config=config,
    )

    assert failed["entities"].budget == Decimal("500")
    assert fresh["entities"].destination == "成都"
    assert fresh["entities"].days == 2
    assert fresh["entities"].budget is None
    assert fresh["budget_feasibility"] is None
    assert fresh["missing_fields"] == ["people", "budget"]


def test_complete_plan_slots_finish_validated_planning_flow() -> None:
    result = invoke("帮我规划成都三日游，两个人，总预算5000，喜欢美食")

    assert result["intent"] == Intent.TRIP_PLAN
    assert result["next_action"] == NextAction.COMPLETE
    assert result["missing_fields"] == []
    assert result["entities"].budget == Decimal("5000")
    assert result["plan_saved"] is True


def test_missing_plan_slots_route_to_ask_user() -> None:
    result = invoke("帮我规划成都三日游")

    assert result["next_action"] == NextAction.ASK_USER
    assert result["missing_fields"] == ["people", "budget"]


def test_modify_and_booking_require_current_plan() -> None:
    missing_plan = invoke("把第二天上午换成熊猫基地")
    modifiable = invoke("把第二天上午换成熊猫基地", current_plan=current_plan())
    bookable = invoke(
        "预订酒店 HOTEL-CD-001",
        current_plan=current_plan(),
    )

    assert missing_plan["missing_fields"] == ["current_plan"]
    assert modifiable["next_action"] == NextAction.ABORT
    assert modifiable["modification_errors"] == ["TARGET_DAY_NOT_FOUND"]
    assert bookable["next_action"] == NextAction.ABORT
    assert bookable["booking_errors"] == [
        "BOOKING_OPTION_NOT_IN_CURRENT_PLAN",
        "BOOKING_OPTION_MISSING_FOR_HOTEL",
    ]


def test_explicit_request_preferences_override_long_term_memory() -> None:
    patch = normalize_state(
        {
            "intent": Intent.TRIP_PLAN,
            "entities": TravelEntities(
                destination="成都",
                days=3,
                people=2,
                budget=Decimal("5000"),
                explicit_preferences=["美食"],
                explicit_dislikes=["购物"],
            ),
            "user_preferences": UserPreferences(
                liked_tags=["购物", "历史文化"],
                disliked_tags=["美食"],
            ),
        }
    )

    effective = patch["effective_preferences"]
    assert effective.liked_tags == ["美食", "历史文化"]
    assert effective.disliked_tags == ["购物"]


def test_unknown_supervisor_action_cannot_invent_a_node() -> None:
    assert route_after_supervisor({"next_action": "invented_node"}) == "abort"


def test_memory_flow_updates_long_term_preferences() -> None:
    result = invoke("记住我喜欢徒步")

    assert result["intent"] is Intent.MEMORY_MANAGE
    assert result["next_action"] is NextAction.COMPLETE
    assert result["user_preferences"].liked_tags == ["徒步"]
    assert result["user_preferences"].source_version == 1
