from langchain_core.messages import AIMessage

from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def validation_failure(state: TravelState) -> TravelStatePatch:
    hard = state.get("hard_validation")
    review = state.get("review_result")
    errors = [issue.code for issue in (hard.errors if hard else [])]
    errors.extend(review.issues if review else [])

    details = [issue.message for issue in (hard.errors if hard else [])][:3]
    if details:
        message = "这版方案仍有硬性问题，所以我先没有保存：" + "；".join(details) + "。"
    else:
        message = "方案经过两轮调整后，体验评审仍未通过，所以我先没有保存。"
    suggestions = (review.suggestions if review else [])[:1]
    if suggestions:
        message += f" 建议下一步：{suggestions[0]}"
    if state.get("current_plan"):
        message += " 已保留上一版有效行程。"

    return {
        "plan_draft": None,
        "plan_saved": False,
        "validation_exhausted": True,
        "planning_errors": list(dict.fromkeys(errors)) or ["VALIDATION_FAILED"],
        "next_action": NextAction.ABORT,
        "messages": [AIMessage(content=message)],
    }
