from app.domain.models import NextAction


# Phase 2 will use this code-owned mapping with add_conditional_edges.
# LLM output may propose an intent, but cannot invent graph destinations.
SUPERVISOR_ROUTE_TARGETS: dict[NextAction, str] = {
    NextAction.ASK_USER: "ask_user",
    NextAction.QUERY_FLOW: "query_entry",
    NextAction.PLANNING_FLOW: "planning_entry",
    NextAction.MODIFY_FLOW: "modify_entry",
    NextAction.MEMORY_FLOW: "memory_entry",
    NextAction.BOOKING_FLOW: "booking_entry",
    NextAction.COMPLETE: "complete",
    NextAction.ABORT: "abort",
}


def route_after_supervisor(state: dict) -> str:
    action = state.get("next_action", NextAction.ABORT)
    try:
        normalized = action if isinstance(action, NextAction) else NextAction(action)
    except ValueError:
        normalized = NextAction.ABORT
    return SUPERVISOR_ROUTE_TARGETS.get(normalized, "abort")
