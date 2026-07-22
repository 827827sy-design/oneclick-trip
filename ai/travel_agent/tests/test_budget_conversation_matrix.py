from datetime import date, timedelta
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.domain.models import (
    BudgetEstimate,
    BudgetMode,
    BudgetScope,
    BudgetTierEstimate,
    Intent,
    NextAction,
    TravelEntities,
)
from app.graph.builder import build_travel_graph
from app.graph.nodes.intent_recognition import _sanitize_explicit_update


def budget_estimate() -> BudgetEstimate:
    return BudgetEstimate(
        survival=BudgetTierEstimate(name="极限穷游", total=Decimal("600")),
        comfortable=BudgetTierEstimate(name="正常舒适", total=Decimal("1800")),
    )


def pending_state(*, estimate: bool = False) -> dict:
    return {
        "intent": Intent.TRIP_PLAN,
        "missing_fields": ["budget_confirmation" if estimate else "budget"],
        "entities": TravelEntities(
            destination="威海",
            origin="成都",
            days=3,
            people=1,
        ),
        "budget_estimate": budget_estimate() if estimate else None,
    }


@pytest.mark.parametrize(
    ("query", "expected_mode"),
    [
        ("帮我估算一下预算", BudgetMode.ESTIMATE),
        ("你帮我估计需要多少钱", BudgetMode.ESTIMATE),
        ("我不知道预算，你帮我算算", BudgetMode.ESTIMATE),
        ("预算大概要多少", BudgetMode.ESTIMATE),
        ("这趟需要多少钱", BudgetMode.ESTIMATE),
        ("帮我算算费用", BudgetMode.ESTIMATE),
        ("尽可能少，帮我估算预算", BudgetMode.MINIMIZE),
        ("按最低预算帮我算", BudgetMode.MINIMIZE),
        ("我想穷游，你估一下多少钱", BudgetMode.MINIMIZE),
        ("越少越好，预算你来估", BudgetMode.MINIMIZE),
        ("能省则省，帮我算算费用", BudgetMode.MINIMIZE),
        ("预算你来估，越省越好", BudgetMode.MINIMIZE),
    ],
)
def test_budget_estimate_phrase_matrix(query: str, expected_mode: BudgetMode) -> None:
    patch = _sanitize_explicit_update(pending_state(), query, {})

    assert patch["budget_mode"] is expected_mode
    assert "budget" not in patch


@pytest.mark.parametrize(
    ("query", "expected_amount", "expected_scope"),
    [
        ("那就1800吧", Decimal("1800"), BudgetScope.TOTAL),
        ("就按1800", Decimal("1800"), BudgetScope.TOTAL),
        ("1800", Decimal("1800"), BudgetScope.TOTAL),
        ("1800元", Decimal("1800"), BudgetScope.TOTAL),
        ("1800左右吧", Decimal("1800"), BudgetScope.TOTAL),
        ("预算控制在1800", Decimal("1800"), BudgetScope.TOTAL),
        ("总共1800", Decimal("1800"), BudgetScope.TOTAL),
        ("总预算1800元", Decimal("1800"), BudgetScope.TOTAL),
        ("人均1800", Decimal("1800"), BudgetScope.PER_PERSON),
        ("每人1800元", Decimal("1800"), BudgetScope.PER_PERSON),
        ("1800元每人", Decimal("1800"), BudgetScope.PER_PERSON),
    ],
)
def test_budget_amount_phrase_matrix(
    query: str,
    expected_amount: Decimal,
    expected_scope: BudgetScope,
) -> None:
    patch = _sanitize_explicit_update(pending_state(estimate=True), query, {})

    assert patch["budget"] == expected_amount
    assert patch["budget_scope"] is expected_scope
    assert patch["budget_mode"] is BudgetMode.FIXED


ARABIC_AMOUNT_CASES = [
    (template.format(amount=amount), Decimal(str(amount)))
    for amount in (100, 399, 500, 999, 1000, 1800, 2500, 5000, 10000, 99999)
    for template in (
        "{amount}",
        "{amount}元",
        "预算{amount}",
        "总预算 {amount} 元",
        "就按{amount}",
        "那就 {amount} 吧",
        "{amount}左右吧",
        "控制在{amount}",
        "总共{amount}",
    )
]


@pytest.mark.parametrize(("query", "expected_amount"), ARABIC_AMOUNT_CASES)
def test_arabic_budget_amount_cross_product(query: str, expected_amount: Decimal) -> None:
    patch = _sanitize_explicit_update(pending_state(estimate=True), query, {})

    assert patch["budget"] == expected_amount
    assert patch["budget_scope"] is BudgetScope.TOTAL


@pytest.mark.parametrize(
    ("query", "expected_amount"),
    [
        ("五百元", Decimal("500")),
        ("预算八百", Decimal("800")),
        ("那就一千吧", Decimal("1000")),
        ("就按一千八百元", Decimal("1800")),
        ("总共两千五百", Decimal("2500")),
        ("人均三千", Decimal("3000")),
        ("总预算一万元", Decimal("10000")),
        ("一万零五百元", Decimal("10500")),
    ],
)
def test_chinese_budget_amount_matrix(query: str, expected_amount: Decimal) -> None:
    patch = _sanitize_explicit_update(pending_state(estimate=True), query, {})

    assert patch["budget"] == expected_amount


@pytest.mark.parametrize(
    "query",
    [
        "玩3天",
        "两个人",
        "2026年8月1日出发",
        "酒店距离景点1800米",
        "高铁需要5小时",
        "每天走10000步",
        "门票有3张",
        "我喜欢500公里以内的目的地",
    ],
)
def test_non_budget_numbers_are_not_misread_as_budget(query: str) -> None:
    patch = _sanitize_explicit_update(pending_state(estimate=True), query, {})

    assert "budget" not in patch


@pytest.mark.parametrize(
    ("query", "expected_amount", "expected_mode"),
    [
        ("选穷游版", Decimal("600"), BudgetMode.MINIMIZE),
        ("按最省的来", Decimal("600"), BudgetMode.MINIMIZE),
        ("预算再省一点", Decimal("600"), BudgetMode.MINIMIZE),
        ("就选便宜的", Decimal("600"), BudgetMode.MINIMIZE),
        ("选舒适版", Decimal("1800"), BudgetMode.FIXED),
        ("正常玩就行", Decimal("1800"), BudgetMode.FIXED),
        ("舒服一点", Decimal("1800"), BudgetMode.FIXED),
    ],
)
def test_budget_tier_selection_phrase_matrix(
    query: str,
    expected_amount: Decimal,
    expected_mode: BudgetMode,
) -> None:
    patch = _sanitize_explicit_update(pending_state(estimate=True), query, {})

    assert patch["budget"] == expected_amount
    assert patch["budget_scope"] is BudgetScope.TOTAL
    assert patch["budget_mode"] is expected_mode


@pytest.mark.parametrize(
    "query",
    [
        "预算降低1000",
        "预算减少 500",
        "预算提高800",
        "预算增加 1200",
        "预算下调300",
        "预算上调 600",
    ],
)
def test_relative_budget_changes_are_not_treated_as_absolute_amounts(query: str) -> None:
    patch = _sanitize_explicit_update(
        pending_state(),
        query,
        {"budget": Decimal("1000"), "budget_scope": BudgetScope.TOTAL},
    )

    assert "budget" not in patch
    assert "budget_scope" not in patch


@pytest.mark.parametrize(
    ("marker", "offset"),
    [("今天", 0), ("明天", 1), ("后天", 2)],
)
def test_relative_date_matrix_uses_system_date(marker: str, offset: int) -> None:
    patch = _sanitize_explicit_update(
        pending_state(),
        f"{marker}出发，玩3天",
        {"days": 3, "start_date": date(2025, 1, 1), "end_date": date(2025, 1, 3)},
    )
    start = date.today() + timedelta(days=offset)

    assert patch["start_date"] == start
    assert patch["end_date"] == start + timedelta(days=2)


def test_date_copied_from_history_is_removed_when_current_turn_has_no_date() -> None:
    patch = _sanitize_explicit_update(
        pending_state(),
        "多安排本地美食",
        {"start_date": date(2025, 1, 1), "end_date": date(2025, 1, 3)},
    )

    assert "start_date" not in patch
    assert "end_date" not in patch


@pytest.mark.parametrize("follow_up", ["多安排本地美食", "我喜欢海鲜", "不要购物景点"])
def test_preference_follow_up_does_not_abandon_pending_trip(follow_up: str) -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    thread_id = f"preference-before-budget-{follow_up}"
    config = {"configurable": {"thread_id": thread_id}}
    first = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [HumanMessage(content="我想去威海玩3天，一个人")],
        },
        config=config,
    )
    second = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [HumanMessage(content=follow_up)],
        },
        config=config,
    )

    assert first["missing_fields"] == ["budget"]
    assert second["intent"] is Intent.TRIP_PLAN
    assert second["entities"].destination == "威海"
    assert second["entities"].days == 3
    assert second["entities"].people == 1
    assert second["next_action"] is NextAction.ASK_USER
    assert second["missing_fields"] == ["budget"]


@pytest.mark.parametrize("selection", ["选穷游版", "按最省的来", "选舒适版", "那就1800吧"])
def test_full_multiturn_budget_selection_completes_plan(selection: str) -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    thread_id = f"budget-selection-{selection}"
    config = {"configurable": {"thread_id": thread_id}}
    first = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [
                HumanMessage(
                    content="从成都去威海，一个人，明天出发，三天两夜，帮我估算预算"
                )
            ],
        },
        config=config,
    )
    second = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [HumanMessage(content=selection)],
        },
        config=config,
    )

    assert first["budget_estimate"] is not None
    assert first["missing_fields"] == ["budget_confirmation"]
    assert second["intent"] is Intent.TRIP_PLAN
    assert second["missing_fields"] == []
    assert second["plan_saved"] is True
    assert second["next_action"] is NextAction.COMPLETE


def test_minimize_plan_presentation_uses_hostel_budget_basis() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    thread_id = "minimize-presentation-basis"
    config = {"configurable": {"thread_id": thread_id}}
    first = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [
                HumanMessage(
                    content=(
                        "从成都去威海，一个人，明天出发，三天两夜，"
                        "帮我估算预算，越省越好"
                    )
                )
            ],
        },
        config=config,
    )
    second = graph.invoke(
        {
            "conversation_id": thread_id,
            "user_id": "budget-matrix-user",
            "messages": [HumanMessage(content="预算再省一点")],
        },
        config=config,
    )

    answer = second["messages"][-1].content
    assert second["entities"].budget == first["budget_estimate"].survival.total
    assert second["entities"].budget_mode is BudgetMode.MINIMIZE
    assert second["plan_saved"] is True
    assert "青旅床位或同级最低价住宿核算" in answer
    assert "普通住宿参考" not in answer
