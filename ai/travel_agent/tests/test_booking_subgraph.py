from datetime import UTC, datetime

import pytest
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.booking import BookingBackendError, MockJavaBookingBackend
from app.domain.models import BookingStatus, NextAction, SelectedOptions
from app.graph.builder import build_travel_graph
from app.memory.checkpoints import InMemoryCheckpointBackend


FULL_PLAN_QUERY = "帮我规划成都三日游，两个人，总预算5000，喜欢美食"


def build_bookable_plan(conversation_id: str, backend: MockJavaBookingBackend | None = None):
    configured_backend = backend or MockJavaBookingBackend()
    graph = build_travel_graph(
        InMemoryCheckpointBackend().create(),
        booking_backend=configured_backend,
    )
    config = {"configurable": {"thread_id": conversation_id}}
    user_id = f"user-{conversation_id}"
    plan = graph.invoke(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "messages": [HumanMessage(content=FULL_PLAN_QUERY)],
        },
        config=config,
    )
    hotel_id = "HOTEL-DEMO-001"
    return graph, config, user_id, plan, hotel_id


def begin_hotel_booking(graph, config, user_id: str, hotel_id: str):
    graph.invoke(
        {
            "conversation_id": config["configurable"]["thread_id"],
            "user_id": user_id,
            "messages": [HumanMessage(content=f"预订酒店 {hotel_id}")],
            "selected_options": SelectedOptions(hotel_option_ids=[hotel_id]),
        },
        config=config,
    )
    return graph.get_state(config)


def test_booking_pauses_with_backend_draft_reference() -> None:
    graph, config, user_id, plan, hotel_id = build_bookable_plan("booking-pause")
    snapshot = begin_hotel_booking(graph, config, user_id, hotel_id)

    assert len(snapshot.interrupts) == 1
    payload = snapshot.interrupts[0].value
    assert payload["kind"] == "booking_confirmation"
    assert payload["plan_id"] == plan["current_plan"].plan_id
    assert payload["plan_version"] == 1
    assert payload["selected_option_ids"] == [hotel_id]
    assert "token" not in payload
    assert "hash" not in payload
    assert "order_id" not in payload


def test_confirm_resume_is_bound_to_same_user_and_plan() -> None:
    graph, config, user_id, _, hotel_id = build_bookable_plan("booking-confirm")
    begin_hotel_booking(graph, config, user_id, hotel_id)

    result = graph.invoke(
        Command(resume={"confirmed": True, "user_id": user_id}),
        config=config,
    )

    assert result["booking_draft"].status is BookingStatus.CONFIRMED
    assert result["booking_completed"] is True
    assert result["booking_errors"] == []
    assert result["next_action"] is NextAction.COMPLETE
    assert graph.get_state(config).interrupts == ()


def test_reject_resume_cancels_without_submission() -> None:
    graph, config, user_id, _, hotel_id = build_bookable_plan("booking-cancel")
    begin_hotel_booking(graph, config, user_id, hotel_id)

    result = graph.invoke(
        Command(resume={"confirmed": False, "user_id": user_id}),
        config=config,
    )

    assert result["booking_draft"].status is BookingStatus.CANCELLED
    assert result["booking_completed"] is False
    assert result["next_action"] is NextAction.COMPLETE


def test_invalid_option_never_creates_interrupt() -> None:
    graph, config, user_id, plan, _ = build_bookable_plan("booking-invalid")
    result = graph.invoke(
        {
            "conversation_id": "booking-invalid",
            "user_id": user_id,
            "messages": [HumanMessage(content="预订酒店 HOTEL-NOT-IN-PLAN")],
        },
        config=config,
    )

    assert graph.get_state(config).interrupts == ()
    assert result["booking_errors"] == ["BOOKING_OPTION_NOT_IN_CURRENT_PLAN", "BOOKING_OPTION_MISSING_FOR_HOTEL"]
    assert result["current_plan"] == plan["current_plan"]
    assert result["next_action"] is NextAction.ABORT


def test_mock_backend_rejects_stale_plan_and_expired_draft() -> None:
    now = datetime(2026, 7, 16, tzinfo=UTC)
    backend = MockJavaBookingBackend(ttl_minutes=0, clock=lambda: now)
    draft = backend.create_booking_draft(
        conversation_id="conversation",
        user_id="user",
        plan_id="PLAN-1",
        plan_version=1,
        booking_types=["hotel"],
        selected_option_ids=["HOTEL-1"],
    )

    with pytest.raises(BookingBackendError, match="current plan") as stale:
        backend.confirm_booking(
            draft_id=draft.draft_id,
            conversation_id="conversation",
            user_id="user",
            plan_id="PLAN-1",
            plan_version=2,
        )
    assert stale.value.code == "DRAFT_PLAN_STALE"

    with pytest.raises(BookingBackendError, match="expired") as expired:
        backend.confirm_booking(
            draft_id=draft.draft_id,
            conversation_id="conversation",
            user_id="user",
            plan_id="PLAN-1",
            plan_version=1,
        )
    assert expired.value.code == "DRAFT_EXPIRED"


def test_mock_backend_confirmation_is_idempotent() -> None:
    backend = MockJavaBookingBackend()
    draft = backend.create_booking_draft(
        conversation_id="conversation",
        user_id="user",
        plan_id="PLAN-1",
        plan_version=1,
        booking_types=["ticket"],
        selected_option_ids=["TICKET-1"],
    )
    kwargs = {
        "draft_id": draft.draft_id,
        "conversation_id": "conversation",
        "user_id": "user",
        "plan_id": "PLAN-1",
        "plan_version": 1,
    }

    first = backend.confirm_booking(**kwargs)
    second = backend.confirm_booking(**kwargs)

    assert first.status is BookingStatus.CONFIRMED
    assert second == first
