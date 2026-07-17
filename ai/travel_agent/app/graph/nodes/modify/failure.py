from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def modification_failure(state: TravelState) -> TravelStatePatch:
    errors = list(state.get("modification_errors") or []) + list(
        state.get("planning_errors") or []
    )
    return {
        "plan_draft": None,
        "plan_saved": False,
        "modification_errors": list(dict.fromkeys(errors)) or ["MODIFICATION_FAILED"],
        "next_action": NextAction.ABORT,
        "messages": [
            AIMessage(
                content="未能安全完成这次行程修改，已保留上一版有效方案。请补充更明确的修改目标。"
            )
        ],
    }
