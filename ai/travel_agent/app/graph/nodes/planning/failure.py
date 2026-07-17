from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def planning_failure(state: TravelState) -> TravelStatePatch:
    errors = list(state.get("planning_errors") or []) + list(
        state.get("candidate_validation_errors") or []
    )
    return {
        "plan_draft": None,
        "plan_saved": False,
        "planning_errors": errors or ["UNKNOWN_PLANNING_ERROR"],
        "next_action": NextAction.ABORT,
        "messages": [
            AIMessage(
                content="方案生成未通过候选来源检查，本次不会保存行程。请稍后重试。"
            )
        ],
    }
