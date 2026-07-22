from decimal import Decimal

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.candidate_selector import LangChainCandidateSelectorAgent
from app.domain.models import (
    CandidateSelection,
    CandidateVisit,
    HotelAreaCandidate,
    NextAction,
    Phase1Research,
    POICandidate,
    ToolName,
    ToolResult,
    TransportCandidate,
    TravelEntities,
)
from app.graph.builder import build_travel_graph
from app.graph.nodes.planning.candidate_validation import candidate_validation


FULL_PLAN_QUERY = "帮我规划成都三日游，两个人，总预算5000，喜欢美食，不要购物"


def test_candidate_normalizer_avoids_full_area_plus_internal_poi_duplication() -> None:
    research = Phase1Research(
        destination="梵净山",
        weather_summary="多云",
        poi_candidates=[
            POICandidate(
                poi_id="AREA",
                name="梵净山景区",
                area="江口县",
                suggested_duration_minutes=480,
            ),
            POICandidate(
                poi_id="PEAK",
                name="红云金顶",
                area="梵净山景区内",
                suggested_duration_minutes=120,
            ),
            POICandidate(
                poi_id="ROCK",
                name="蘑菇石",
                area="梵净山景区内",
                suggested_duration_minutes=60,
            ),
            POICandidate(
                poi_id="VILLAGE",
                name="寨沙侗寨",
                area="江口县",
                suggested_duration_minutes=120,
            ),
        ],
    )
    selection = CandidateSelection(
        selected_poi_ids=["AREA", "PEAK", "ROCK"],
        selected_pois=[
            CandidateVisit(
                poi_id=poi_id,
                visit_date="DAY_1",
                estimated_duration_minutes=duration,
            )
            for poi_id, duration in (("AREA", 480), ("PEAK", 120), ("ROCK", 60))
        ],
    )

    normalized = LangChainCandidateSelectorAgent._normalize(
        selection,
        research,
        TravelEntities(destination="梵净山", days=2),
    )

    assert normalized.selected_poi_ids == ["VILLAGE", "AREA"]
    assert [visit.visit_date for visit in normalized.selected_pois] == ["DAY_1", "DAY_2"]


def test_candidate_validation_rejects_unavailable_placeholder_research() -> None:
    research = Phase1Research(
        data_mode="UNAVAILABLE",
        destination="新疆",
        weather_summary="天气服务不可用",
        poi_candidates=[
            POICandidate(
                poi_id="AI-POI-1",
                name="新疆第 1 项当地体验",
                area="待核实区域",
                suggested_duration_minutes=120,
            )
        ],
        hotel_areas=[
            HotelAreaCandidate(
                area_id="AI-AREA-1",
                name="新疆公共交通便利区域",
                reason="待核实",
            )
        ],
    )
    patch = candidate_validation(
        {
            "phase1_research": research,
            "candidate_selection": CandidateSelection(
                selected_poi_ids=["AI-POI-1"],
                selected_pois=[
                    CandidateVisit(
                        poi_id="AI-POI-1",
                        visit_date="DAY_1",
                        estimated_duration_minutes=120,
                    )
                ],
                destinations=["AI-POI-1"],
                hotel_area_id="AI-AREA-1",
            ),
        }
    )

    assert "PLACEHOLDER_RESEARCH_NOT_SAVEABLE" in patch["candidate_validation_errors"]
    assert "UNGROUNDED_RESEARCH_NOT_SAVEABLE" in patch["candidate_validation_errors"]


def test_complete_trip_request_generates_typed_plan_draft() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "planning-1",
            "user_id": "user-1",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
        }
    )

    draft = result["plan_draft"]
    assert draft is not None
    assert draft.destination == "成都"
    assert len(draft.days) == 3
    assert draft.hotel_nights == 2
    assert draft.total_cost > Decimal("0")
    assert draft.days[0].date is None
    assert draft.days[0].items[0].start_at is None
    assert draft.days[0].items[0].start_time is not None
    assert result["planning_errors"] == []
    assert "AI 通用知识建议" in result["messages"][-1].content
    assert result["hard_validation"].hard_pass is True
    assert result["review_result"].verdict == "pass"
    assert result["plan_saved"] is True


def test_validated_draft_is_promoted_to_current_plan() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "planning-2",
            "user_id": "user-2",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
        }
    )

    assert result["plan_draft"] is not None
    assert result["current_plan"] == result["plan_draft"]
    assert result["plan_version"] == 1


def test_multistage_plan_uses_only_validated_research_candidates() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "planning-3",
            "user_id": "user-3",
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
        }
    )

    selected_ids = set(result["candidate_selection"].selected_poi_ids)
    plan_ids = {
        item.location_id
        for day in result["plan_draft"].days
        for item in day.items
        if item.location_id
    }
    assert result["phase1_research"].data_mode == "TEST_FIXTURE"
    assert result["phase2_research"].data_mode == "TEST_FIXTURE"
    assert set(result["candidate_selection"].selected_poi_ids).issubset(
        {item.poi_id for item in result["phase1_research"].poi_candidates}
    )
    assert [
        visit.poi_id for visit in result["candidate_selection"].selected_pois
    ] == result["candidate_selection"].selected_poi_ids
    assert result["candidate_selection"].destinations == result["candidate_selection"].selected_poi_ids
    assert all(
        visit.visit_date.startswith("DAY_")
        for visit in result["candidate_selection"].selected_pois
    )
    assert selected_ids == plan_ids
    assert all(value.startswith("AI-POI-") for value in selected_ids)


def test_infeasible_budget_stops_before_planner_and_requests_adjustment() -> None:
    result = build_travel_graph().invoke(
        {
            "conversation_id": "budget-feasibility",
            "user_id": "budget-user",
            "messages": [
                HumanMessage(content="帮我规划从成都去大理三日游，一个人，总预算500元")
            ],
        }
    )

    feasibility = result["budget_feasibility"]
    assert feasibility.feasible is False
    assert feasibility.budget_limit == Decimal("500")
    assert feasibility.estimated_minimum == Decimal("1490")
    assert feasibility.suggested_budget == Decimal("1500")
    assert result["next_action"] is NextAction.ASK_USER
    assert result["missing_fields"] == ["budget"]
    assert result["revision_count"] == 0
    assert result["plan_draft"] is None
    assert result["planning_errors"] == ["AI_BUDGET_INFEASIBLE"]
    assert "保守估算约需 1490 元" in result["messages"][-1].content
    assert "route_matrix" not in result["selected_tools"]


def test_budget_adjustment_continues_pending_plan_without_repeating_slots() -> None:
    graph = build_travel_graph(checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "budget-adjustment"}}
    first = graph.invoke(
        {
            "conversation_id": "budget-adjustment",
            "user_id": "budget-user",
            "messages": [
                HumanMessage(content="帮我规划从成都去大理三日游，一个人，总预算500元")
            ],
        },
        config=config,
    )
    second = graph.invoke(
        {
            "conversation_id": "budget-adjustment",
            "user_id": "budget-user",
            "messages": [HumanMessage(content="总预算2500元")],
        },
        config=config,
    )

    assert first["next_action"] is NextAction.ASK_USER
    assert second["entities"].destination == "大理"
    assert second["entities"].days == 3
    assert second["entities"].people == 1
    assert second["entities"].budget == Decimal("2500")
    assert second["next_action"] is NextAction.COMPLETE
    assert second["plan_saved"] is True


def test_candidate_validator_rejects_ids_not_returned_by_research() -> None:
    research = Phase1Research(
        destination="成都",
        weather_summary="DEMO",
        poi_candidates=[
            POICandidate(
                poi_id="POI-VALID",
                name="合法景点",
                area="中心城区",
                suggested_duration_minutes=120,
            )
        ],
        hotel_areas=[
            HotelAreaCandidate(
                area_id="AREA-VALID",
                name="合法区域",
                reason="测试",
            )
        ],
        transport_options=[
            TransportCandidate(
                option_id="TRAIN-VALID",
                mode="train",
                name="合法交通",
                duration_minutes=60,
            )
        ],
    )
    patch = candidate_validation(
        {
            "phase1_research": research,
            "candidate_selection": CandidateSelection(
                selected_poi_ids=["POI-HALLUCINATED"],
                selected_pois=[
                    CandidateVisit(
                        poi_id="POI-HALLUCINATED",
                        visit_date="DAY_1",
                        estimated_duration_minutes=120,
                    )
                ],
                destinations=["POI-HALLUCINATED"],
                hotel_area_id="AREA-INVALID",
                transport_option_id="FLIGHT-INVALID",
            ),
        }
    )

    assert patch["candidate_validation_errors"] == [
        "UNKNOWN_POI_IDS:POI-HALLUCINATED",
        "UNKNOWN_HOTEL_AREA:AREA-INVALID",
        "UNKNOWN_TRANSPORT_OPTION:FLIGHT-INVALID",
    ]


def test_candidate_validator_does_not_force_irrelevant_knowledge_hit_usage() -> None:
    research = Phase1Research(
        data_mode="AI_KNOWLEDGE",
        destination="成都",
        weather_summary="多云",
        poi_candidates=[
            POICandidate(
                poi_id="AI-POI-1",
                name="武侯祠",
                area="武侯区",
                suggested_duration_minutes=120,
            )
        ],
    )
    patch = candidate_validation(
        {
            "phase1_research": research,
            "candidate_selection": CandidateSelection(
                selected_poi_ids=["AI-POI-1"],
                selected_pois=[
                    CandidateVisit(
                        poi_id="AI-POI-1",
                        visit_date="DAY_1",
                        estimated_duration_minutes=120,
                    )
                ],
                destinations=["AI-POI-1"],
            ),
            "tool_results": {
                ToolName.KNOWLEDGE_SEARCH.value: ToolResult(
                    success=True,
                    data={
                        "hits": [
                            {
                                "document_id": "xinjiang-guide",
                                "text": "新疆七日游攻略",
                            }
                        ]
                    },
                )
            },
        }
    )

    assert patch["candidate_validation_errors"] == []
