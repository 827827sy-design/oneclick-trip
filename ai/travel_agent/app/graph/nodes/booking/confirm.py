from collections.abc import Callable

from langchain_core.messages import AIMessage

from app.booking.contracts import BookingBackend, BookingBackendError
from app.domain.models import BookingStatus, NextAction
from app.graph.state import TravelState, TravelStatePatch


def make_confirm_booking_node(
    backend: BookingBackend,
) -> Callable[[TravelState], TravelStatePatch]:
    def confirm_booking(state: TravelState) -> TravelStatePatch:
        return _change_booking_status(state, backend=backend, confirm=True)

    return confirm_booking


def make_cancel_booking_node(
    backend: BookingBackend,
) -> Callable[[TravelState], TravelStatePatch]:
    def cancel_booking(state: TravelState) -> TravelStatePatch:
        return _change_booking_status(state, backend=backend, confirm=False)

    return cancel_booking


def _change_booking_status(
    state: TravelState,
    *,
    backend: BookingBackend,
    confirm: bool,
) -> TravelStatePatch:
    draft = state.get("booking_draft")
    plan = state.get("current_plan")
    if draft is None or plan is None:
        return {"booking_errors": ["BOOKING_DRAFT_MISSING"], "next_action": NextAction.ABORT}
    operation = backend.confirm_booking if confirm else backend.cancel_booking
    try:
        updated = operation(
            draft_id=draft.draft_id,
            conversation_id=state["conversation_id"],
            user_id=state["user_id"],
            plan_id=plan.plan_id,
            plan_version=plan.version,
        )
    except BookingBackendError as exc:
        failed_draft = draft
        if exc.code == "DRAFT_EXPIRED":
            failed_draft = draft.model_copy(update={"status": BookingStatus.EXPIRED})
        return {
            "booking_draft": failed_draft,
            "booking_errors": [exc.code],
            "booking_completed": False,
            "next_action": NextAction.ABORT,
        }

    action = "确认" if confirm else "取消"
    return {
        "booking_draft": updated,
        "booking_errors": [],
        "booking_completed": confirm,
        "checkpoint_version": state.get("checkpoint_version", 0) + 1,
        "next_action": NextAction.COMPLETE,
        "messages": [
            AIMessage(
                content=(
                    f"预订草稿 {updated.draft_id} 已{action}。"
                    "当前结果来自 Java Backend Mock，不包含真实支付或供应商下单。"
                )
            )
        ],
    }
