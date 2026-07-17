from app.domain.models import Intent, NextAction, SelectedOptions, TravelEntities, UserPreferences
from app.graph.state import TravelState, TravelStatePatch


def normalize_state(state: TravelState) -> TravelStatePatch:
    """Apply deterministic slot rules and current-request memory precedence."""
    entities = state.get("entities") or TravelEntities()
    long_term = state.get("user_preferences") or UserPreferences()
    effective = merge_preferences(long_term, entities)
    missing_fields = required_fields_for_intent(state, entities)
    return {
        "entities": entities,
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
        if not (entities.days or (entities.start_date and entities.end_date)):
            missing.append("duration")
        if not entities.people:
            missing.append("people")
        if entities.budget is None:
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
