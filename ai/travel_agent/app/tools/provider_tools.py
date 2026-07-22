from __future__ import annotations

from app.domain.models import Phase1Research, ToolDataMode, ToolResult
from app.tools.contracts import ToolContext
from app.tools.providers.contracts import (
    PoiCoordinateProvider,
    PoiCoordinateQuery,
    PoiCoordinateRequest,
    RouteMatrixRequest,
    RoutePoint,
    RouteProvider,
    WeatherProvider,
    WeatherRequest,
)


class PoiCoordinateProviderTool:
    is_realtime_provider = True

    def __init__(self, provider: PoiCoordinateProvider) -> None:
        self._provider = provider

    def __call__(self, context: ToolContext) -> ToolResult:
        phase1 = context.phase1_research
        destination = context.entities.destination
        if not phase1 or not destination or not phase1.poi_candidates:
            return ToolResult(
                success=False,
                source="poi-coordinate-provider",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "景点定位缺少目的地或候选景点"},
                error_code="POI_COORDINATE_INPUT_MISSING",
                retryable=False,
            )
        return self._provider.resolve_coordinates(
            PoiCoordinateRequest(
                destination=destination,
                pois=[
                    PoiCoordinateQuery(poi_id=poi.poi_id, name=poi.name)
                    for poi in phase1.poi_candidates
                ],
            )
        )


def apply_verified_coordinates(
    research: Phase1Research,
    result: ToolResult,
) -> Phase1Research:
    if not result.success:
        return research
    resolved = {
        str(item.get("poi_id")): item
        for item in result.data.get("resolved", [])
        if item.get("poi_id")
    }
    candidates = []
    for candidate in research.poi_candidates:
        coordinates = resolved.get(candidate.poi_id)
        if not coordinates:
            candidates.append(candidate)
            continue
        candidates.append(
            candidate.model_copy(
                update={
                    "latitude": float(coordinates["latitude"]),
                    "longitude": float(coordinates["longitude"]),
                    "coordinate_source": result.source,
                    "coordinates_verified": True,
                }
            )
        )
    return research.model_copy(update={"poi_candidates": candidates})


class WeatherProviderTool:
    is_realtime_provider = True

    def __init__(self, provider: WeatherProvider) -> None:
        self._provider = provider

    def __call__(self, context: ToolContext) -> ToolResult:
        destination = context.entities.destination
        if not destination:
            return ToolResult(
                success=False,
                source="weather-provider",
                data_mode=ToolDataMode.REALTIME,
                data={"message": "天气查询缺少目的地"},
                error_code="WEATHER_DESTINATION_MISSING",
                retryable=False,
            )
        return self._provider.get_forecast(
            WeatherRequest(
                destination=destination,
                start_date=context.entities.start_date,
                end_date=context.entities.end_date,
            )
        )


class RouteProviderTool:
    is_realtime_provider = True

    def __init__(self, provider: RouteProvider) -> None:
        self._provider = provider

    def __call__(self, context: ToolContext) -> ToolResult:
        phase1 = context.phase1_research
        selection = context.candidate_selection
        if not phase1 or not selection:
            return _missing_coordinates("路线查询缺少候选景点或选择结果")
        candidates = {candidate.poi_id: candidate for candidate in phase1.poi_candidates}
        points = []
        for poi_id in selection.selected_poi_ids:
            candidate = candidates.get(poi_id)
            if (
                not candidate
                or candidate.latitude is None
                or candidate.longitude is None
                or not candidate.coordinates_verified
                or not candidate.coordinate_source
            ):
                return _missing_coordinates(f"景点 {poi_id} 缺少已验证坐标")
            points.append(
                RoutePoint(
                    point_id=poi_id,
                    name=candidate.name,
                    latitude=candidate.latitude,
                    longitude=candidate.longitude,
                )
            )
        if len(points) < 2:
            return _missing_coordinates("路线查询至少需要两个带坐标的景点")
        return self._provider.get_route(RouteMatrixRequest(points=points))


def _missing_coordinates(message: str) -> ToolResult:
    return ToolResult(
        success=False,
        source="route-provider",
        data_mode=ToolDataMode.REALTIME,
        data={"message": message},
        error_code="ROUTE_COORDINATES_MISSING",
        retryable=False,
    )
