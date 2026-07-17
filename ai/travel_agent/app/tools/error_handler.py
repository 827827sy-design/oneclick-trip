from __future__ import annotations

from decimal import Decimal

from app.domain.models import ToolName, ToolRecoveryAction, ToolResult
from app.tools.contracts import ToolContext


FALLBACK_TOOLS = {
    ToolName.WEATHER,
    ToolName.ROUTE_MATRIX,
    ToolName.OPENING_HOURS,
    ToolName.TICKET,
}

ABORT_TOOLS = {ToolName.HOTEL_SEARCH, ToolName.POI_SEARCH}


class ToolErrorHandler:
    """Deterministic retry/fallback/continue/abort policy."""

    def decide(
        self,
        tool_name: ToolName,
        result: ToolResult,
        attempt: int,
    ) -> ToolRecoveryAction:
        if result.retryable and attempt < 2:
            return ToolRecoveryAction.RETRY
        if tool_name in FALLBACK_TOOLS:
            return ToolRecoveryAction.FALLBACK
        if tool_name in ABORT_TOOLS:
            return ToolRecoveryAction.ABORT
        return ToolRecoveryAction.CONTINUE

    def fallback(self, tool_name: ToolName, context: ToolContext) -> ToolResult:
        selected_ids = (
            context.candidate_selection.selected_poi_ids
            if context.candidate_selection
            else []
        )
        if tool_name is ToolName.WEATHER:
            data = {
                "data_mode": "FALLBACK",
                "summary": "天气服务暂不可用，请在出发前再次确认实时天气。",
            }
        elif tool_name is ToolName.ROUTE_MATRIX:
            data = {
                "data_mode": "FALLBACK",
                "route_legs": [
                    {
                        "from_id": start,
                        "to_id": end,
                        "distance_km": 5.0,
                        "duration_minutes": 35,
                    }
                    for start, end in zip(selected_ids, selected_ids[1:])
                ],
            }
        elif tool_name is ToolName.OPENING_HOURS:
            data = {
                "data_mode": "FALLBACK",
                "opening_hours": [
                    {"poi_id": poi_id, "opening_hours": "开放时间待人工确认"}
                    for poi_id in selected_ids
                ],
            }
        else:
            data = {
                "data_mode": "FALLBACK",
                "tickets": [
                    {
                        "poi_id": poi_id,
                        "ticket_option_id": None,
                        "ticket_price": str(Decimal("0")),
                        "available": False,
                    }
                    for poi_id in selected_ids
                ],
            }
        return ToolResult(success=True, data=data, error_code="FALLBACK_USED")
