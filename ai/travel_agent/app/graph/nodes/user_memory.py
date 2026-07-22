from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime as DateTime

from langchain_core.messages import AIMessage

from app.database.contracts import UserPreferenceRepository
from app.domain.models import NextAction, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def persist_observed_preferences(state: TravelState) -> TravelStatePatch:
    return _preference_patch(state, include_message=False)


def manage_user_preferences(state: TravelState) -> TravelStatePatch:
    return _preference_patch(state, include_message=True)


def make_persist_observed_preferences_node(
    repository: UserPreferenceRepository,
    *,
    include_message: bool = False,
) -> Callable[[TravelState], TravelStatePatch]:
    async def persist(state: TravelState) -> TravelStatePatch:
        patch = _preference_patch(state, include_message=include_message)
        if patch.get("memory_errors") or "user_preferences" not in patch:
            return patch
        preferences = patch["user_preferences"]
        try:
            await repository.save(state["user_id"], preferences)
        except Exception:
            failure: TravelStatePatch = {
                "memory_errors": ["USER_PREFERENCE_PERSISTENCE_FAILED"]
            }
            if include_message:
                failure.update(
                    {
                        "messages": [AIMessage(content="旅行偏好暂时无法保存，请稍后重试。")],
                        "next_action": NextAction.ABORT,
                    }
                )
            return failure
        return patch

    return persist


def _preference_patch(state: TravelState, *, include_message: bool) -> TravelStatePatch:
    entities = state.get("entities")
    current = state.get("user_preferences") or UserPreferences()
    if entities is None or (not entities.explicit_preferences and not entities.explicit_dislikes):
        return {"memory_errors": []}

    explicit_likes = list(dict.fromkeys(entities.explicit_preferences))
    explicit_dislikes = list(dict.fromkeys(entities.explicit_dislikes))
    liked = explicit_likes + [
        tag
        for tag in current.liked_tags
        if tag not in explicit_likes and tag not in explicit_dislikes
    ]
    disliked = explicit_dislikes + [
        tag
        for tag in current.disliked_tags
        if tag not in explicit_likes and tag not in explicit_dislikes
    ]
    updated = current.model_copy(
        update={
            "liked_tags": liked,
            "disliked_tags": disliked,
            "source_version": current.source_version + 1,
            "updated_at": DateTime.now(UTC),
        }
    )
    patch: TravelStatePatch = {
        "user_preferences": updated,
        "effective_preferences": updated,
        "memory_errors": [],
    }
    if include_message:
        patch.update(
            {
                "messages": [
                    AIMessage(
                        content=(
                            f"已更新旅行偏好：喜欢 {', '.join(liked) or '暂无'}；"
                            f"不喜欢 {', '.join(disliked) or '暂无'}。"
                        )
                    )
                ],
                "next_action": NextAction.COMPLETE,
            }
        )
    return patch
