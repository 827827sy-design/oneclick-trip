from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def planning_failure(state: TravelState) -> TravelStatePatch:
    errors = list(state.get("planning_errors") or []) + list(
        state.get("candidate_validation_errors") or []
    )
    destination = (state.get("entities").destination if state.get("entities") else None) or "目的地"
    ungrounded = any(
        error in {"PLACEHOLDER_RESEARCH_NOT_SAVEABLE", "UNGROUNDED_RESEARCH_NOT_SAVEABLE"}
        for error in errors
    )
    message = (
        f"目前没有找到足够可靠的{destination}景点与路线资料，这次不会生成或保存占位方案。"
        "可以换成更具体的城市或区域，或稍后重试联网检索。"
        if ungrounded
        else "方案生成未通过候选来源检查，本次不会保存行程。请稍后重试。"
    )
    return {
        "plan_draft": None,
        "plan_saved": False,
        "planning_errors": errors or ["UNKNOWN_PLANNING_ERROR"],
        "next_action": NextAction.ABORT,
        "messages": [
            AIMessage(content=message)
        ],
    }
