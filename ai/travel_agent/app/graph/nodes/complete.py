from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def complete(_: TravelState) -> TravelStatePatch:
    return {"next_action": NextAction.COMPLETE}
