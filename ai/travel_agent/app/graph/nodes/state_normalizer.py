from app.domain.models import (
    BudgetMode,
    Intent,
    NextAction,
    SelectedOptions,
    TravelEntities,
    UserPreferences,
)
from app.graph.state import TravelState, TravelStatePatch


REGION_LEVEL_DESTINATIONS = {
    "新疆", "西藏", "云南", "四川", "贵州", "海南", "青海", "甘肃", "内蒙古", "广西", "福建",
}


ONE_OFF_MEMORY_MARKERS = ("这次", "本次", "这趟", "只去", "只玩", "只逛", "本趟", "总预算")
STABLE_MEMORY_MARKERS = ("以后", "通常", "一直", "每次", "总是", "习惯", "长期", "从不", "都喜欢")


def normalize_state(state: TravelState) -> TravelStatePatch:
    """Apply deterministic slot rules and current-request memory precedence."""
    entities = state.get("entities") or TravelEntities()
    long_term = sanitize_preferences(state.get("user_preferences") or UserPreferences())
    effective = merge_preferences(long_term, entities)
    missing_fields = required_fields_for_intent(state, entities)
    return {
        "entities": entities,
        "user_preferences": long_term,
        "missing_fields": missing_fields,
        "effective_preferences": effective,
        "selected_options": state.get("selected_options") or SelectedOptions(),
        "revision_count": max(state.get("revision_count", 0), 0),
        "next_action": NextAction.SUPERVISE,
    }


def merge_preferences(long_term: UserPreferences, entities: TravelEntities) -> UserPreferences:
    explicit_dislikes = list(dict.fromkeys(entities.explicit_dislikes))
    explicit_likes = [tag for tag in dict.fromkeys(entities.explicit_preferences) if tag not in explicit_dislikes]
    liked = explicit_likes + [
        tag for tag in long_term.liked_tags if tag not in explicit_dislikes and tag not in explicit_likes
    ]
    disliked = explicit_dislikes + [
        tag for tag in long_term.disliked_tags if tag not in explicit_likes and tag not in explicit_dislikes
    ]
    return long_term.model_copy(update={"liked_tags": liked, "disliked_tags": disliked})


def sanitize_preferences(preferences: UserPreferences) -> UserPreferences:
    """Remove legacy one-off trip facts that were accidentally stored as habits."""
    retained_items = []
    removed_likes: set[str] = set()
    removed_dislikes: set[str] = set()
    for item in preferences.memory_items:
        evidence = item.evidence.strip()
        one_off = any(marker in evidence for marker in ONE_OFF_MEMORY_MARKERS)
        stable = any(marker in evidence for marker in STABLE_MEMORY_MARKERS)
        generic_other = item.value in {"其他景点", "其它景点", "别的景点"}
        contaminated = (one_off and not stable) or generic_other
        if contaminated:
            if item.category == "avoidance":
                removed_dislikes.add(item.value)
            elif item.category in {"food", "hotel", "activity", "tag"}:
                removed_likes.add(item.value)
            continue
        retained_items.append(item)

    liked = [item for item in preferences.liked_tags if item not in removed_likes]
    disliked = [
        item
        for item in preferences.disliked_tags
        if item not in removed_dislikes and item not in {"其他景点", "其它景点", "别的景点"}
    ]
    if (
        retained_items == preferences.memory_items
        and liked == preferences.liked_tags
        and disliked == preferences.disliked_tags
    ):
        return preferences
    return preferences.model_copy(
        update={
            "memory_items": retained_items,
            "liked_tags": liked,
            "disliked_tags": disliked,
            "source_version": preferences.source_version + 1,
        }
    )


def required_fields_for_intent(state: TravelState, entities: TravelEntities) -> list[str]:
    intent = state.get("intent", Intent.UNKNOWN)
    missing: list[str] = []
    if intent in {Intent.WEATHER_QUERY, Intent.HOTEL_QUERY}:
        if not entities.destination:
            missing.append("destination")
    elif intent is Intent.TRANSPORT_QUERY:
        if not entities.origin:
            missing.append("origin")
        if not entities.destination:
            missing.append("destination")
    elif intent is Intent.TRIP_PLAN:
        if not entities.destination:
            missing.append("destination")
        elif entities.destination in REGION_LEVEL_DESTINATIONS:
            missing.append("destination_detail")
        if not (entities.days or (entities.start_date and entities.end_date)):
            missing.append("duration")
        if not entities.people:
            missing.append("people")
        if (
            entities.budget is None
            and entities.budget_mode in {BudgetMode.ESTIMATE, BudgetMode.MINIMIZE}
            and not entities.origin
        ):
            missing.append("origin")
        if entities.budget is None and entities.budget_mode not in {
            BudgetMode.ESTIMATE,
            BudgetMode.MINIMIZE,
        }:
            missing.append("budget")
    elif intent is Intent.MODIFY_PLAN:
        if not state.get("current_plan"):
            missing.append("current_plan")
    elif intent is Intent.BOOKING:
        if not state.get("current_plan"):
            missing.append("current_plan")
        if not entities.booking_types:
            missing.append("booking_type")
        if not entities.selected_option_ids:
            missing.append("selected_option_ids")
    elif intent is Intent.BOOKING_CONFIRM:
        if not state.get("booking_draft"):
            missing.append("booking_draft")
    elif intent is Intent.MEMORY_MANAGE:
        if not entities.explicit_preferences and not entities.explicit_dislikes:
            missing.append("preference_update")
    elif intent is Intent.UNKNOWN:
        missing.append("intent")
    return missing
