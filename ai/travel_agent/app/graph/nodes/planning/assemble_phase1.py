from app.domain.models import (
    HotelAreaCandidate,
    Phase1Research,
    POICandidate,
    ToolName,
    TransportCandidate,
    TravelEntities,
)
from app.graph.state import TravelState, TravelStatePatch


def assemble_phase1_research(state: TravelState) -> TravelStatePatch:
    if state.get("tool_abort_requested"):
        return {"planning_errors": ["PHASE1_TOOL_ABORT"]}

    results = state.get("tool_results", {})
    weather = results.get(ToolName.WEATHER.value)
    hotels = results.get(ToolName.HOTEL_SEARCH.value)
    pois = results.get(ToolName.POI_SEARCH.value)
    missing = [
        name.value
        for name, result in (
            (ToolName.WEATHER, weather),
            (ToolName.HOTEL_SEARCH, hotels),
            (ToolName.POI_SEARCH, pois),
        )
        if result is None or not result.success
    ]
    if missing:
        return {"planning_errors": [f"PHASE1_REQUIRED_TOOLS_FAILED:{','.join(missing)}"]}

    transport_options: list[TransportCandidate] = []
    for tool_name in (ToolName.TRAIN_SEARCH, ToolName.FLIGHT_SEARCH):
        result = results.get(tool_name.value)
        if result and result.success:
            transport_options.extend(
                TransportCandidate.model_validate(option)
                for option in result.data.get("options", [])
            )

    entities = state.get("entities") or TravelEntities()
    return {
        "phase1_research": Phase1Research(
            data_mode="MOCK",
            destination=entities.destination or "未指定目的地",
            weather_summary=str(weather.data.get("summary", "天气待确认")),
            poi_candidates=[
                POICandidate.model_validate(item)
                for item in pois.data.get("candidates", [])
            ],
            hotel_areas=[
                HotelAreaCandidate.model_validate(item)
                for item in hotels.data.get("areas", [])
            ],
            transport_options=transport_options,
        )
    }
