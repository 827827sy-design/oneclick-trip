from collections.abc import Callable

from app.database.contracts import PlanRepository
from app.domain.models import NextAction
from app.graph.state import TravelState, TravelStatePatch


def load_conversation_state(state: TravelState) -> TravelStatePatch:
    """Validate graph identity after the checkpointer has hydrated the thread."""
    if not state.get("conversation_id"):
        raise ValueError("conversation_id is required")
    if not state.get("user_id"):
        raise ValueError("user_id is required")
    return {
        "checkpoint_version": max(state.get("checkpoint_version", 0), 0),
        "next_action": NextAction.LOAD_USER_MEMORY,
    }


def make_load_conversation_state_node(
    repository: PlanRepository,
) -> Callable[[TravelState], TravelStatePatch]:
    async def load_persisted_conversation(state: TravelState) -> TravelStatePatch:
        base = load_conversation_state(state)
        if state.get("current_plan") is not None:
            return base
        persisted = await repository.get_current(state["user_id"], state["conversation_id"])
        if persisted is None:
            return base
        return {
            **base,
            "current_plan": persisted.plan,
            "plan_version": persisted.plan.version,
            "entities": persisted.entities,
            "selected_options": persisted.selected_options,
            "candidate_selection": persisted.candidate_selection,
            "phase1_research": persisted.phase1_research,
            "phase2_research": persisted.phase2_research,
        }

    return load_persisted_conversation
