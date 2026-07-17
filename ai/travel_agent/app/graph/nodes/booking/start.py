from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def start_booking(_: TravelState) -> TravelStatePatch:
    return {
        "booking_draft": None,
        "booking_errors": [],
        "booking_confirmation": None,
        "booking_interrupted": False,
        "booking_completed": False,
        "next_action": NextAction.BOOKING_FLOW,
    }
