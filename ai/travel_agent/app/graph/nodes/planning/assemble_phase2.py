from decimal import Decimal

from app.domain.models import Phase2Research, POIVisitDetail, RouteLeg, ToolName
from app.graph.state import TravelState, TravelStatePatch


def assemble_phase2_research(state: TravelState) -> TravelStatePatch:
    if state.get("tool_abort_requested"):
        return {"planning_errors": ["PHASE2_TOOL_ABORT"]}

    selection = state.get("candidate_selection")
    if selection is None:
        return {"planning_errors": ["CANDIDATE_SELECTION_MISSING"]}
    results = state.get("tool_results", {})
    route_result = results.get(ToolName.ROUTE_MATRIX.value)
    opening_result = results.get(ToolName.OPENING_HOURS.value)
    ticket_result = results.get(ToolName.TICKET.value)
    missing = [
        name.value
        for name, result in (
            (ToolName.ROUTE_MATRIX, route_result),
            (ToolName.OPENING_HOURS, opening_result),
            (ToolName.TICKET, ticket_result),
        )
        if result is None or not result.success
    ]
    if missing:
        return {"planning_errors": [f"PHASE2_TOOLS_FAILED:{','.join(missing)}"]}

    opening_by_id = {
        item["poi_id"]: item["opening_hours"]
        for item in opening_result.data.get("opening_hours", [])
    }
    ticket_by_id = {
        item["poi_id"]: item
        for item in ticket_result.data.get("tickets", [])
    }
    details: list[POIVisitDetail] = []
    for poi_id in selection.selected_poi_ids:
        ticket = ticket_by_id.get(poi_id, {})
        details.append(
            POIVisitDetail(
                poi_id=poi_id,
                opening_hours=opening_by_id.get(poi_id, "开放时间待确认"),
                ticket_option_id=ticket.get("ticket_option_id"),
                ticket_price=Decimal(str(ticket.get("ticket_price", "0"))),
                available=bool(ticket.get("available", False)),
            )
        )
    return {
        "phase2_research": Phase2Research(
            data_mode="MOCK",
            route_legs=[
                RouteLeg.model_validate(item)
                for item in route_result.data.get("route_legs", [])
            ],
            poi_details=details,
        )
    }
