from collections.abc import Callable

from app.booking.contracts import BookingBackend, BookingBackendError
from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def make_create_booking_draft_node(
    backend: BookingBackend,
) -> Callable[[TravelState], TravelStatePatch]:
    def create_booking_draft(state: TravelState) -> TravelStatePatch:
        plan = state.get("current_plan")
        entities = state.get("entities")
        if plan is None or entities is None:
            return {"booking_errors": ["BOOKING_STATE_INCOMPLETE"]}
        try:
            draft = backend.create_booking_draft(
                conversation_id=state["conversation_id"],
                user_id=state["user_id"],
                plan_id=plan.plan_id,
                plan_version=plan.version,
                booking_types=entities.booking_types,
                selected_option_ids=entities.selected_option_ids,
            )
        except BookingBackendError as exc:
            return {"booking_errors": [exc.code], "next_action": NextAction.ABORT}
        return {
            "booking_draft": draft,
            "booking_interrupted": True,
            "booking_completed": False,
        }

    return create_booking_draft
