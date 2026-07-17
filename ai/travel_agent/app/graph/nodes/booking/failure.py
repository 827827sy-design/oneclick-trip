from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def booking_failure(state: TravelState) -> TravelStatePatch:
    errors = state.get("booking_errors") or ["BOOKING_FLOW_FAILED"]
    return {
        "booking_completed": False,
        "booking_interrupted": False,
        "next_action": NextAction.ABORT,
        "messages": [AIMessage(content=f"预订流程未提交：{', '.join(errors)}")],
    }
