from datetime import date, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.intent_agent import RuleBasedIntentAgent, enforce_code_owned_intent
from app.domain.models import (
    BudgetMode,
    BudgetScope,
    Intent,
    IntentDecision,
    NextAction,
    TravelEntities,
    TravelPlan,
    UserPreferences,
)
from app.graph.builder import build_travel_graph
from app.graph.nodes.state_normalizer import normalize_state
from app.graph.router import route_after_supervisor
from app.tools.mock_tools import build_mock_tool_registry


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


class UnknownIntentAgent(RuleBasedIntentAgent):
    def classify(self, query: str, *, context=None):
        del query, context
        return IntentDecision(intent=Intent.UNKNOWN, confidence=0.8)

    async def aclassify(self, query: str, *, context=None):
        return self.classify(query, context=context)


class OverplanningIntentAgent(RuleBasedIntentAgent):
    def classify(self, query: str, *, context=None):
        decision = super().classify(query, context=context)
        return decision.model_copy(update={"intent": Intent.TRIP_PLAN, "tasks": []})

    async def aclassify(self, query: str, *, context=None):
        return self.classify(query, context=context)


class ConfidentlyWrongIntentAgent(RuleBasedIntentAgent):
    def classify(self, query: str, *, context=None):
        del query, context
        return IntentDecision(intent=Intent.GENERAL_QA, confidence=0.99)

    async def aclassify(self, query: str, *, context=None):
        return self.classify(query, context=context)


def test_rule_agent_extracts_transport_direction_in_text_order() -> None:
    decision = RuleBasedIntentAgent().classify("成都到上海怎么去方便？")

    assert decision.intent == Intent.TRANSPORT_QUERY
    assert decision.entities.origin == "成都"
    assert decision.entities.destination == "上海"


def test_rule_agent_extracts_multiple_read_only_intents() -> None:
    decision = RuleBasedIntentAgent().classify(
        "查成都明天天气，顺便推荐两家酒店"
    )

    assert decision.intent is Intent.WEATHER_QUERY
    assert [task.intent for task in decision.tasks] == [
        Intent.WEATHER_QUERY,
        Intent.HOTEL_QUERY,
    ]
    assert all(task.entities.destination == "成都" for task in decision.tasks)


def test_rule_agent_keeps_source_requirement_with_the_question() -> None:
    query = "成都有哪些历史文化景点？请说明开放时间，并标明资料来源。"

    decision = RuleBasedIntentAgent().classify(query)

    assert decision.intent is Intent.GENERAL_QA
    assert len(decision.tasks) == 1
    assert decision.tasks[0].query == "成都有哪些历史文化景点？请说明开放时间，并标明资料来源"


def test_relative_weather_date_and_visit_word_do_not_trigger_trip_plan() -> None:
    decision = RuleBasedIntentAgent().classify(
        "请查询成都明天的天气，并推荐两个适合第一次去成都游客的住宿区域。"
    )

    assert decision.intent is Intent.WEATHER_QUERY
    assert [task.intent for task in decision.tasks] == [
        Intent.WEATHER_QUERY,
        Intent.HOTEL_QUERY,
    ]
    assert all(task.entities.destination == "成都" for task in decision.tasks)


def test_code_guard_repairs_unknown_model_compound_intent() -> None:
    result = build_travel_graph(intent_agent=UnknownIntentAgent()).invoke(
        {
            "conversation_id": "unknown-compound",
            "user_id": "unknown-compound-user",
            "messages": [
                HumanMessage(content="查成都明天天气，顺便推荐两家酒店")
            ],
        }
    )

    assert result["intent"] is Intent.WEATHER_QUERY
    assert [task.intent for task in result["intent_tasks"]] == [
        Intent.WEATHER_QUERY,
        Intent.HOTEL_QUERY,
    ]


def test_code_guard_repairs_confident_weather_misclassification() -> None:
    result = build_travel_graph(
        intent_agent=ConfidentlyWrongIntentAgent(),
        tool_registry=build_mock_tool_registry(),
    ).invoke(
        {
            "conversation_id": "confident-weather-misroute",
            "user_id": "confident-weather-user",
            "messages": [HumanMessage(content="成都明天天气怎么样？")],
        }
    )

    assert result["intent"] is Intent.WEATHER_QUERY
    assert [task.intent for task in result["intent_tasks"]] == [Intent.WEATHER_QUERY]
    assert result["selected_tools"] == ["weather"]


def test_code_guard_repairs_confident_compound_misclassification() -> None:
    result = build_travel_graph(
        intent_agent=ConfidentlyWrongIntentAgent(),
        tool_registry=build_mock_tool_registry(),
    ).invoke(
        {
            "conversation_id": "confident-compound-misroute",
            "user_id": "confident-compound-user",
            "messages": [HumanMessage(content="查成都明天天气，顺便推荐两家酒店")],
        }
    )

    assert result["intent"] is Intent.WEATHER_QUERY
    assert [task.intent for task in result["intent_tasks"]] == [
        Intent.WEATHER_QUERY,
        Intent.HOTEL_QUERY,
    ]
    assert result["selected_tools"] == ["weather", "hotel_search"]


def test_code_owned_routes_cover_controlled_business_flows() -> None:
    wrong = IntentDecision(intent=Intent.GENERAL_QA, confidence=0.99)
    cases = {
        "成都酒店推荐": Intent.HOTEL_QUERY,
        "上海到成都怎么去方便？": Intent.TRANSPORT_QUERY,
        "帮我规划成都三日游": Intent.TRIP_PLAN,
        "把第二天上午换成熊猫基地": Intent.MODIFY_PLAN,
        "帮我预订酒店 HOTEL-CD-001": Intent.BOOKING,
        "确认预订": Intent.BOOKING_CONFIRM,
        "记住我喜欢徒步": Intent.MEMORY_MANAGE,
    }

    for query, expected in cases.items():
        guarded = enforce_code_owned_intent(query, wrong)
        assert guarded.intent is expected, query


def test_code_route_preserves_llm_destination_outside_rule_dictionary() -> None:
    model_decision = IntentDecision(
        intent=Intent.GENERAL_QA,
        confidence=0.96,
        entities=TravelEntities(destination="阿尔山"),
    )

    guarded = enforce_code_owned_intent("帮我规划阿尔山三日游", model_decision)

    assert guarded.intent is Intent.TRIP_PLAN
    assert guarded.entities.destination == "阿尔山"
    assert guarded.entities.days == 3
    assert guarded.tasks[0].entities.destination == "阿尔山"


def test_code_guard_keeps_route_advice_as_read_only_query() -> None:
    result = build_travel_graph(intent_agent=OverplanningIntentAgent()).invoke(
        {
            "conversation_id": "overplanned-route-advice",
            "user_id": "overplanned-route-advice-user",
            "messages": [
                HumanMessage(content="新疆北疆的喀纳斯和禾木怎么安排更合理？")
            ],
        }
    )

    assert result["intent"] is Intent.GENERAL_QA
    assert result["missing_fields"] == []


def test_trip_plan_absorbs_weather_and_hotel_requirements() -> None:
    decision = RuleBasedIntentAgent().classify(
        "帮我规划成都三日游，两个人，总预算5000，同时考虑天气和酒店"
    )

    assert decision.intent is Intent.TRIP_PLAN
    assert [task.intent for task in decision.tasks] == [Intent.TRIP_PLAN]


def test_booking_request_is_not_parallelized_with_read_only_queries() -> None:
    decision = RuleBasedIntentAgent().classify(
        "查成都天气，并帮我预订酒店"
    )

    assert decision.intent is Intent.BOOKING
    assert [task.intent for task in decision.tasks] == [Intent.BOOKING]


def test_rule_agent_extracts_origin_for_explicit_trip_direction() -> None:
    decision = RuleBasedIntentAgent().classify(
        "帮我规划从成都去大理三日游，一个人，总预算500元"
    )

    assert decision.intent == Intent.TRIP_PLAN
    assert decision.entities.origin == "成都"
    assert decision.entities.destination == "大理"


def test_rule_agent_treats_single_city_from_phrase_as_origin() -> None:
    decision = RuleBasedIntentAgent().classify("我从广州出发")

    assert decision.entities.origin == "广州"
    assert decision.entities.destination is None


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
    assert result["missing_fields"] == ["destination_detail", "duration", "people", "budget"]
    assert result["messages"][-1].content == "再告诉我主要想玩的城市或区域，我就可以接着帮你规划。"
    assert result["clarification_reply"].title == "新疆已经记下啦"
    assert result["clarification_reply"].choice_prompt == "这个范围很大，先选这次主要想玩的城市或区域"
    assert [action.label for action in result["clarification_reply"].actions] == [
        "乌鲁木齐周边",
        "伊犁",
        "喀什",
        "阿勒泰",
    ]


def test_rule_agent_understands_one_week_as_seven_days() -> None:
    decision = RuleBasedIntentAgent().classify("我想去新疆玩一周")

    assert decision.intent is Intent.TRIP_PLAN
    assert decision.entities.destination == "新疆"
    assert decision.entities.days == 7


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
    assert second["next_action"] == NextAction.ASK_USER
    assert second["missing_fields"] == ["destination_detail"]

    third = graph.invoke(
        {
            "conversation_id": "xinjiang-follow-up",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="这次主要玩伊犁")],
        },
        config=config,
    )
    assert third["entities"].destination == "伊犁"
    assert third["next_action"] == NextAction.COMPLETE
    assert third["plan_saved"] is True


def test_choice_actions_advance_people_then_budget_estimate() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "guided-choice-flow"}}
    first = graph.invoke(
        {
            "conversation_id": "guided-choice-flow",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="帮我规划成都三日游")],
        },
        config=config,
    )
    people_action = first["clarification_reply"].actions[0]
    second = graph.invoke(
        {
            "conversation_id": "guided-choice-flow",
            "user_id": "routing-user",
            "messages": [HumanMessage(content=people_action.message)],
        },
        config=config,
    )
    estimate_action = next(
        action
        for action in second["clarification_reply"].actions
        if action.id == "budget-auto-estimate"
    )
    third = graph.invoke(
        {
            "conversation_id": "guided-choice-flow",
            "user_id": "routing-user",
            "messages": [HumanMessage(content=estimate_action.message)],
        },
        config=config,
    )

    assert first["missing_fields"] == ["people", "budget"]
    assert people_action.message == "一共1个人"
    assert second["intent"] is Intent.TRIP_PLAN
    assert second["missing_fields"] == ["budget"]
    assert second["clarification_reply"].choice_prompt == "选一个总预算，也可以直接输入其他金额"
    assert third["intent"] is Intent.TRIP_PLAN
    assert third["missing_fields"] == ["origin"]
    assert third.get("budget_estimate") is None

    fourth = graph.invoke(
        {
            "conversation_id": "guided-choice-flow",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="我从广州出发")],
        },
        config=config,
    )
    assert fourth["missing_fields"] == ["budget_confirmation"]
    assert fourth["budget_estimate"] is not None
    assert len(fourth["clarification_reply"].actions) == 2


def test_agent_estimates_two_budget_tiers_without_reasking_for_budget() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "budget-estimate-follow-up"}}
    first = graph.invoke(
        {
            "conversation_id": "budget-estimate-follow-up",
            "user_id": "routing-user",
            "messages": [
                HumanMessage(
                    content=(
                        "我想从成都去威海，一个人，今天出发，三天两夜，"
                        "你帮我估计一下需要多少预算，尽可能少"
                    )
                )
            ],
        },
        config=config,
    )

    estimate = first["budget_estimate"]
    assert first["next_action"] is NextAction.ASK_USER
    assert first["missing_fields"] == ["budget_confirmation"]
    assert first["entities"].budget is None
    assert first["entities"].budget_mode is BudgetMode.MINIMIZE
    assert first["entities"].start_date == date.today()
    assert first["entities"].end_date == date.today() + timedelta(days=2)
    assert estimate.survival.total < estimate.comfortable.total
    assert "青旅床位或同级最低价住宿" in estimate.survival.assumptions
    assert "泡面、便利店和基础饱腹餐" in estimate.survival.assumptions
    assert "正常体验当地餐饮，不以泡面为主" in estimate.comfortable.assumptions
    assert "极限穷游" in first["messages"][-1].content
    assert "正常舒适" in first["messages"][-1].content
    assert [action.field for action in first["clarification_reply"].actions] == [
        "budget_confirmation",
        "budget_confirmation",
    ]
    assert first["clarification_reply"].actions[0].recommended is True
    assert "极限穷游" in first["clarification_reply"].actions[0].message

    second = graph.invoke(
        {
            "conversation_id": "budget-estimate-follow-up",
            "user_id": "routing-user",
            "messages": [HumanMessage(content="那就1800吧，你帮我安排行程")],
        },
        config=config,
    )

    assert second["intent"] is Intent.TRIP_PLAN
    assert second["entities"].budget == Decimal("1800")
    assert second["entities"].budget_scope is BudgetScope.TOTAL
    assert second["entities"].budget_mode is BudgetMode.FIXED
    assert second["missing_fields"] == []
    assert second["plan_saved"] is True


def test_colloquial_intercity_trip_without_from_is_still_a_plan() -> None:
    decision = RuleBasedIntentAgent().classify(
        "广州去厦门，2个人，明天出发，4天，帮我算算费用"
    )

    assert decision.intent is Intent.TRIP_PLAN
    assert decision.entities.origin == "广州"
    assert decision.entities.destination == "厦门"
    assert decision.entities.days == 4
    assert decision.entities.people == 2
    assert decision.entities.budget_mode is BudgetMode.ESTIMATE


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
