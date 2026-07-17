from app.graph.state import TravelState, TravelStatePatch


def candidate_validation(state: TravelState) -> TravelStatePatch:
    research = state.get("phase1_research")
    selection = state.get("candidate_selection")
    errors: list[str] = []
    if research is None:
        errors.append("PHASE1_RESEARCH_MISSING")
    if selection is None:
        errors.append("CANDIDATE_SELECTION_MISSING")
    if errors:
        return {"candidate_validation_errors": errors}

    allowed_pois = {item.poi_id for item in research.poi_candidates}
    allowed_areas = {item.area_id for item in research.hotel_areas}
    allowed_transport = {item.option_id for item in research.transport_options}
    unknown_pois = sorted(set(selection.selected_poi_ids) - allowed_pois)
    visit_ids = [visit.poi_id for visit in selection.selected_pois]
    if not selection.selected_poi_ids:
        errors.append("NO_POI_SELECTED")
    if unknown_pois:
        errors.append(f"UNKNOWN_POI_IDS:{','.join(unknown_pois)}")
    if visit_ids != selection.selected_poi_ids:
        errors.append("SELECTED_VISITS_MISMATCH")
    if selection.destinations != selection.selected_poi_ids:
        errors.append("ROUTE_DESTINATIONS_MISMATCH")
    if selection.hotel_area_id and selection.hotel_area_id not in allowed_areas:
        errors.append(f"UNKNOWN_HOTEL_AREA:{selection.hotel_area_id}")
    if selection.transport_option_id and selection.transport_option_id not in allowed_transport:
        errors.append(f"UNKNOWN_TRANSPORT_OPTION:{selection.transport_option_id}")
    return {"candidate_validation_errors": errors}
