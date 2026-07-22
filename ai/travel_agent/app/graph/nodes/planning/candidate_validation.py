import re

from app.domain.models import ToolName
from app.graph.state import TravelState, TravelStatePatch


PLACEHOLDER_POI_PATTERN = re.compile(r"第\s*\d+\s*项当地体验")


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
    placeholder_pois = [
        item for item in research.poi_candidates if PLACEHOLDER_POI_PATTERN.search(item.name)
    ]
    placeholder_areas = [
        item
        for item in research.hotel_areas
        if "公共交通便利区域" in item.name or item.name == "待核实区域"
    ]
    if not research.poi_candidates:
        errors.append("NO_RELIABLE_POI_CANDIDATES")
    if placeholder_pois or placeholder_areas:
        errors.append("PLACEHOLDER_RESEARCH_NOT_SAVEABLE")
    if research.data_mode == "UNAVAILABLE":
        errors.append("UNGROUNDED_RESEARCH_NOT_SAVEABLE")
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
    knowledge_result = (state.get("tool_results") or {}).get(
        ToolName.KNOWLEDGE_SEARCH.value
    )
    knowledge_hits = (
        list(knowledge_result.data.get("hits") or [])
        if knowledge_result is not None and knowledge_result.success
        else []
    )
    if knowledge_hits:
        retrieved_ids = {
            str(hit.get("document_id"))
            for hit in knowledge_hits
            if hit.get("document_id")
        }
        selected_candidates = [
            item for item in research.poi_candidates
            if item.poi_id in selection.selected_poi_ids
        ]
        invalid_sources = sorted(
            {
                document_id
                for item in selected_candidates
                for document_id in item.source_document_ids
                if document_id not in retrieved_ids
            }
        )
        if invalid_sources:
            errors.append(
                f"UNKNOWN_KNOWLEDGE_DOCUMENT_IDS:{','.join(invalid_sources)}"
            )
        selected_uses_knowledge = any(
            item.source_document_ids for item in selected_candidates
        )
        if research.data_mode == "RAG_HYBRID" and not selected_uses_knowledge:
            errors.append("KNOWLEDGE_RESULTS_NOT_USED")
        if selected_uses_knowledge and (
            research.data_mode != "RAG_HYBRID"
        ):
            errors.append("KNOWLEDGE_DATA_MODE_MISMATCH")
    return {"candidate_validation_errors": list(dict.fromkeys(errors))}
