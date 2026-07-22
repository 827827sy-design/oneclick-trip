from collections.abc import Callable

from app.database.contracts import UserPreferenceRepository
from app.domain.models import NextAction, UserPreferences
from app.graph.nodes.state_normalizer import sanitize_preferences
from app.graph.state import TravelState, TravelStatePatch


def load_user_memory(state: TravelState) -> TravelStatePatch:
    """In-memory fallback used by tests and local isolated graphs."""
    if state.get("ignore_user_preferences"):
        return {
            "user_preferences": UserPreferences(),
            "next_action": NextAction.RECOGNIZE_INTENT,
        }
    preferences = sanitize_preferences(
        state.get("user_preferences") or UserPreferences()
    )
    return {
        "user_preferences": preferences,
        "next_action": NextAction.RECOGNIZE_INTENT,
    }


def make_load_user_memory_node(
    repository: UserPreferenceRepository,
) -> Callable[[TravelState], TravelStatePatch]:
    async def load_persisted_user_memory(state: TravelState) -> TravelStatePatch:
        if state.get("ignore_user_preferences"):
            return {
                "user_preferences": UserPreferences(),
                "next_action": NextAction.RECOGNIZE_INTENT,
            }
        preferences = await repository.get_by_user_id(state["user_id"])
        sanitized = sanitize_preferences(preferences)
        if sanitized != preferences:
            await repository.save(state["user_id"], sanitized)
        return {
            "user_preferences": sanitized,
            "next_action": NextAction.RECOGNIZE_INTENT,
        }

    return load_persisted_user_memory
