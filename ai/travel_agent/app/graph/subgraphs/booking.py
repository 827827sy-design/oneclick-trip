from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.booking.contracts import BookingBackend
from app.graph.nodes.booking import (
    booking_failure,
    booking_slot_guard,
    make_cancel_booking_node,
    make_confirm_booking_node,
    make_create_booking_draft_node,
    wait_for_booking_confirmation,
)
from app.graph.state import TravelState


def route_after_slot_guard(state: TravelState) -> str:
    return "fail" if state.get("booking_errors") else "create"


def route_after_draft_creation(state: TravelState) -> str:
    return "fail" if state.get("booking_errors") or not state.get("booking_draft") else "wait"


def route_after_confirmation(state: TravelState) -> str:
    if state.get("booking_errors"):
        return "fail"
    return "confirm" if state.get("booking_confirmation") is True else "cancel"


def route_after_backend_call(state: TravelState) -> str:
    return "fail" if state.get("booking_errors") else "done"


def build_booking_subgraph(*, backend: BookingBackend) -> CompiledStateGraph:
    graph = StateGraph(TravelState)
    graph.add_node("booking_slot_guard", booking_slot_guard)
    graph.add_node("create_booking_draft", make_create_booking_draft_node(backend))
    graph.add_node("wait_for_confirmation", wait_for_booking_confirmation)
    graph.add_node("confirm_booking", make_confirm_booking_node(backend))
    graph.add_node("cancel_booking", make_cancel_booking_node(backend))
    graph.add_node("booking_failure", booking_failure)

    graph.add_edge(START, "booking_slot_guard")
    graph.add_conditional_edges(
        "booking_slot_guard",
        route_after_slot_guard,
        {"create": "create_booking_draft", "fail": "booking_failure"},
    )
    graph.add_conditional_edges(
        "create_booking_draft",
        route_after_draft_creation,
        {"wait": "wait_for_confirmation", "fail": "booking_failure"},
    )
    graph.add_conditional_edges(
        "wait_for_confirmation",
        route_after_confirmation,
        {
            "confirm": "confirm_booking",
            "cancel": "cancel_booking",
            "fail": "booking_failure",
        },
    )
    graph.add_conditional_edges(
        "confirm_booking",
        route_after_backend_call,
        {"done": END, "fail": "booking_failure"},
    )
    graph.add_conditional_edges(
        "cancel_booking",
        route_after_backend_call,
        {"done": END, "fail": "booking_failure"},
    )
    graph.add_edge("booking_failure", END)
    return graph.compile()
