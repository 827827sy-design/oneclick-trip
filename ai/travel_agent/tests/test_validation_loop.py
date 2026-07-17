from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from langchain_core.messages import HumanMessage

from app.agents.revision_agent import LangChainRevisionAgent
from app.domain.models import (
    BookingDraft,
    BookingStatus,
    HardValidationResult,
    ItineraryDay,
    ItineraryItem,
    NextAction,
    Phase2Research,
    POIVisitDetail,
    ReviewResult,
    ReviewVerdict,
    TravelEntities,
    TravelPlan,
)
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend
from app.validators.hard_validator import HardValidator


FULL_PLAN_QUERY = "帮我规划成都三日游，两个人，总预算5000，喜欢美食"


class FailOnceReviewer:
    def __init__(self) -> None:
        self.calls = 0

    def review(self, *_) -> ReviewResult:
        self.calls += 1
        if self.calls == 1:
            return ReviewResult(
                verdict=ReviewVerdict.REVISE,
                score=70,
                issues=["DEMO_REVISION_REQUIRED"],
                suggestions=["重新排列时间"],
            )
        return ReviewResult(verdict=ReviewVerdict.PASS, score=95)

    async def areview(self, *args) -> ReviewResult:
        return self.review(*args)


class AlwaysReviseReviewer:
    def review(self, *_) -> ReviewResult:
        return ReviewResult(
            verdict=ReviewVerdict.REVISE,
            score=40,
            issues=["EXPERIENCE_NOT_ACCEPTABLE"],
        )

    async def areview(self, *args) -> ReviewResult:
        return self.review(*args)


def invoke_plan(**state_overrides):
    return build_travel_graph(
        reviewer_agent=state_overrides.pop("reviewer_agent", None)
    ).invoke(
        {
            "conversation_id": "validation-loop",
            "user_id": "validation-user",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
            **state_overrides,
        }
    )


def test_hard_validator_reports_code_owned_constraint_errors() -> None:
    plan = TravelPlan(
        plan_id="PLAN-INVALID",
        version=1,
        destination="成都",
        hotel_nights=1,
        total_cost=Decimal("500"),
        days=[
            ItineraryDay(
                day_index=1,
                items=[
                    ItineraryItem(
                        item_id="I-1",
                        name="景点一",
                        location_id="POI-1",
                        start_time=time(9, 0),
                        end_time=time(11, 0),
                        visit_minutes=120,
                    ),
                    ItineraryItem(
                        item_id="I-2",
                        name="景点二",
                        location_id="POI-2",
                        start_time=time(10, 0),
                        end_time=time(12, 0),
                        visit_minutes=120,
                    ),
                ],
            )
        ],
    )
    phase2 = Phase2Research(
        poi_details=[
            POIVisitDetail(poi_id="POI-1", opening_hours="09:00-10:00"),
            POIVisitDetail(poi_id="POI-2", opening_hours="09:00-18:00"),
        ]
    )
    result = HardValidator().validate(
        plan,
        TravelEntities(destination="成都", days=1, people=1, budget=Decimal("100")),
        phase2,
    )

    codes = {issue.code for issue in result.errors}
    assert result.hard_pass is False
    assert {
        "HOTEL_NIGHTS_MISMATCH",
        "BUDGET_EXCEEDED",
        "TIME_CONFLICT",
        "OUTSIDE_OPENING_HOURS",
    } <= codes


def test_hard_validator_rejects_duplicate_poi_across_days() -> None:
    plan = TravelPlan(
        plan_id="PLAN-DUPLICATE",
        version=1,
        destination="成都",
        hotel_nights=1,
        days=[
            ItineraryDay(
                day_index=1,
                items=[
                    ItineraryItem(
                        item_id="D1-I1",
                        name="宽窄巷子",
                        location_id="POI-1",
                        start_time=time(9, 0),
                        end_time=time(11, 0),
                    )
                ],
            ),
            ItineraryDay(
                day_index=2,
                items=[
                    ItineraryItem(
                        item_id="D2-I1",
                        name="宽窄巷子",
                        location_id="POI-1",
                        start_time=time(9, 0),
                        end_time=time(11, 0),
                    )
                ],
            ),
        ],
    )
    result = HardValidator().validate(
        plan,
        TravelEntities(destination="成都", days=2),
        Phase2Research(
            poi_details=[POIVisitDetail(poi_id="POI-1", opening_hours="09:00-18:00")]
        ),
    )

    assert result.hard_pass is False
    assert "DUPLICATE_POI" in {issue.code for issue in result.errors}


def test_revision_repairs_opening_hours_and_small_budget_estimate_margin() -> None:
    plan = TravelPlan(
        plan_id="PLAN-FANJINGSHAN",
        version=1,
        destination="梵净山",
        hotel_nights=1,
        total_cost=Decimal("1010"),
        days=[
            ItineraryDay(
                day_index=1,
                items=[
                    ItineraryItem(
                        item_id="D1-I1",
                        name="梵净山景区",
                        location_id="POI-1",
                        description="开放时间参考：08:00-15:00。",
                        travel_minutes=20,
                        visit_minutes=480,
                    ),
                    ItineraryItem(
                        item_id="D1-I2",
                        name="承恩寺",
                        location_id="POI-2",
                        description="开放时间参考：08:00-15:00。",
                        travel_minutes=15,
                        visit_minutes=60,
                    ),
                ],
            ),
            ItineraryDay(
                day_index=2,
                items=[
                    ItineraryItem(
                        item_id="D2-I1",
                        name="红云金顶",
                        location_id="POI-3",
                        description="开放时间参考：08:00-15:00。",
                        travel_minutes=60,
                        visit_minutes=120,
                    ),
                    ItineraryItem(
                        item_id="D2-I2",
                        name="蘑菇石",
                        location_id="POI-4",
                        description="开放时间参考：08:00-15:00。",
                        travel_minutes=30,
                        visit_minutes=60,
                    ),
                ],
            ),
        ],
    )
    phase2 = Phase2Research(
        poi_details=[
            POIVisitDetail(poi_id=f"POI-{index}", opening_hours="08:00-15:00")
            for index in range(1, 5)
        ]
    )

    LangChainRevisionAgent._repair_schedule_with_opening_hours(plan)
    result = HardValidator().validate(
        plan,
        TravelEntities(
            destination="梵净山",
            days=2,
            people=1,
            budget=Decimal("1000"),
        ),
        phase2,
    )

    assert result.hard_pass is True
    assert [len(day.items) for day in plan.days] == [1, 3]
    assert "BUDGET_ESTIMATE_MARGIN" in {warning.code for warning in result.warnings}


def test_soft_review_failure_can_pass_after_one_revision() -> None:
    reviewer = FailOnceReviewer()
    result = invoke_plan(reviewer_agent=reviewer)

    assert reviewer.calls == 2
    assert result["revision_count"] == 1
    assert result["hard_validation"].hard_pass is True
    assert result["review_result"].verdict is ReviewVerdict.PASS
    assert result["plan_saved"] is True
    assert result["current_plan"] is not None


def test_infeasible_budget_is_rejected_before_revision_loop() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "budget-failure",
            "user_id": "budget-user",
            "messages": [
                HumanMessage(content="帮我规划成都三日游，两个人，总预算1000")
            ],
        }
    )

    assert result["revision_count"] == 0
    assert result["hard_validation"] is None
    assert result["plan_saved"] is False
    assert result["validation_exhausted"] is False
    assert result["plan_draft"] is None
    assert result.get("current_plan") is None
    assert result["planning_errors"] == ["AI_BUDGET_INFEASIBLE"]
    assert result["next_action"] is NextAction.ASK_USER
    assert result["budget_feasibility"].feasible is False


def test_failed_revision_keeps_previous_valid_plan() -> None:
    previous = TravelPlan(
        plan_id="PLAN-PREVIOUS",
        version=7,
        destination="成都",
    )
    result = invoke_plan(
        reviewer_agent=AlwaysReviseReviewer(),
        current_plan=previous,
        plan_version=7,
    )

    assert result["revision_count"] == 2
    assert result["plan_saved"] is False
    assert result["current_plan"] == previous
    assert result["plan_version"] == 7
    assert result["plan_draft"] is None
    assert "已保留上一版有效行程" in result["messages"][-1].content


def test_new_valid_version_clears_old_booking_draft() -> None:
    graph = build_travel_graph(InMemoryCheckpointBackend().create())
    config = {"configurable": {"thread_id": "versioned-plan"}}
    first = graph.invoke(
        {
            "conversation_id": "versioned-plan",
            "user_id": "versioned-user",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
        },
        config=config,
    )
    old_draft = BookingDraft(
        draft_id="DRAFT-OLD",
        status=BookingStatus.PENDING_CONFIRMATION,
        conversation_id="versioned-plan",
        user_id="versioned-user",
        plan_id=first["current_plan"].plan_id,
        plan_version=1,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    second = graph.invoke(
        {
            "conversation_id": "versioned-plan",
            "user_id": "versioned-user",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
            "booking_draft": old_draft,
        },
        config=config,
    )

    assert second["plan_saved"] is True
    assert second["plan_version"] == 2
    assert second["current_plan"].version == 2
    assert second["current_plan"].plan_id == first["current_plan"].plan_id
    assert second["booking_draft"] is None
    assert second["checkpoint_version"] == 2
