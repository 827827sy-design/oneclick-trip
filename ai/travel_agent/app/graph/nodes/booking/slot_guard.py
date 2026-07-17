from app.graph.state import TravelState, TravelStatePatch


SUPPORTED_BOOKING_TYPES = {"hotel", "train", "flight", "ticket"}


def booking_slot_guard(state: TravelState) -> TravelStatePatch:
    plan = state.get("current_plan")
    entities = state.get("entities")
    selected = state.get("selected_options")
    errors: list[str] = []
    if plan is None:
        errors.append("CURRENT_PLAN_MISSING")
    if entities is None or not entities.booking_types:
        errors.append("BOOKING_TYPE_MISSING")
    if entities is None or not entities.selected_option_ids:
        errors.append("BOOKING_OPTION_MISSING")
    if errors or entities is None or selected is None:
        return {"booking_errors": errors or ["BOOKING_STATE_INCOMPLETE"]}

    unknown_types = set(entities.booking_types) - SUPPORTED_BOOKING_TYPES
    if unknown_types:
        errors.append("BOOKING_TYPE_NOT_ALLOWED")

    options_by_type = {
        "hotel": set(selected.hotel_option_ids),
        "train": {value for value in selected.transport_option_ids if value.startswith("TRAIN-")},
        "flight": {value for value in selected.transport_option_ids if value.startswith("FLIGHT-")},
        "ticket": set(selected.ticket_option_ids),
    }
    requested_ids = set(entities.selected_option_ids)
    allowed_ids = set().union(*(options_by_type[kind] for kind in entities.booking_types if kind in options_by_type))
    if not requested_ids.issubset(allowed_ids):
        errors.append("BOOKING_OPTION_NOT_IN_CURRENT_PLAN")
    for booking_type in entities.booking_types:
        if booking_type in options_by_type and not (requested_ids & options_by_type[booking_type]):
            errors.append(f"BOOKING_OPTION_MISSING_FOR_{booking_type.upper()}")

    return {"booking_errors": list(dict.fromkeys(errors))}
