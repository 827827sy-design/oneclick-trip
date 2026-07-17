from langgraph.types import interrupt

from app.graph.state import TravelState, TravelStatePatch


def wait_for_booking_confirmation(state: TravelState) -> TravelStatePatch:
    draft = state.get("booking_draft")
    plan = state.get("current_plan")
    if draft is None or plan is None:
        return {"booking_errors": ["BOOKING_DRAFT_MISSING"]}

    answer = interrupt(
        {
            "kind": "booking_confirmation",
            "draft_id": draft.draft_id,
            "plan_id": draft.plan_id,
            "plan_version": draft.plan_version,
            "booking_types": draft.booking_types,
            "selected_option_ids": draft.selected_option_ids,
            "expires_at": draft.expires_at.isoformat(),
            "message": "订单草稿已创建，请确认或取消预订。",
        }
    )
    if not isinstance(answer, dict) or not isinstance(answer.get("confirmed"), bool):
        return {
            "booking_errors": ["INVALID_CONFIRMATION_PAYLOAD"],
            "booking_interrupted": False,
        }
    if answer.get("user_id") != state.get("user_id"):
        return {
            "booking_errors": ["CONFIRMATION_USER_MISMATCH"],
            "booking_interrupted": False,
        }
    if draft.plan_id != plan.plan_id or draft.plan_version != plan.version:
        return {
            "booking_errors": ["DRAFT_PLAN_STALE"],
            "booking_interrupted": False,
        }
    return {
        "booking_confirmation": answer["confirmed"],
        "booking_interrupted": False,
    }
