from app.domain.models import Intent, NextAction
from app.graph.state import TravelState, TravelStatePatch


QUERY_INTENTS = {
    Intent.WEATHER_QUERY,
    Intent.HOTEL_QUERY,
    Intent.TRANSPORT_QUERY,
    Intent.GENERAL_QA,
}


def supervisor(state: TravelState) -> TravelStatePatch:
    """Choose a business flow from a closed, code-owned intent mapping."""
    if state.get("missing_fields"):
        return {"next_action": NextAction.ASK_USER}

    intent = state.get("intent", Intent.UNKNOWN)
    if intent in QUERY_INTENTS:
        action = NextAction.QUERY_FLOW
    elif intent is Intent.TRIP_PLAN:
        action = NextAction.PLANNING_FLOW
    elif intent is Intent.MODIFY_PLAN:
        action = NextAction.MODIFY_FLOW
    elif intent in {Intent.BOOKING, Intent.BOOKING_CONFIRM}:
        action = NextAction.BOOKING_FLOW
    elif intent is Intent.MEMORY_MANAGE:
        action = NextAction.MEMORY_FLOW
    else:
        action = NextAction.ABORT
    return {"next_action": action}
