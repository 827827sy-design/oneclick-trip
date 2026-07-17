from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch
from app.graph.tool_runtime import reset_tool_execution


def start_query(_: TravelState) -> TravelStatePatch:
    return {
        **reset_tool_execution(),
        "next_action": NextAction.QUERY_FLOW,
    }
