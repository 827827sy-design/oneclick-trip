from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.agents.query_presenter import LangChainQueryPresenterAgent
from app.domain.models import (
    CandidateSelection,
    Phase1Research,
    POICandidate,
    ToolDataMode,
    ToolName,
    TravelEntities,
    ToolResult,
)
from app.tools.contracts import ToolContext
from app.tools.executor import ToolExecutor
from app.tools.factory import build_knowledge_research_registry, build_live_tool_registry
from app.tools.provider_tools import (
    RouteProviderTool,
    apply_verified_coordinates,
)
from app.tools.providers import (
    NominatimPoiCoordinateProvider,
    OpenMeteoWeatherProvider,
    OsrmRouteProvider,
    PoiCoordinateQuery,
    PoiCoordinateRequest,
    RouteMatrixRequest,
    RoutePoint,
    WeatherRequest,
)
from app.tools.registry import ToolRegistry
from app.config import load_settings


def test_open_meteo_provider_returns_normalized_realtime_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/search"):
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "成都",
                            "admin1": "四川",
                            "country": "中国",
                            "latitude": 30.67,
                            "longitude": 104.07,
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Shanghai",
                "current": {"temperature_2m": 26.2, "weather_code": 2},
                "daily": {
                    "time": ["2026-07-20"],
                    "weather_code": [2],
                    "temperature_2m_max": [29.4],
                    "temperature_2m_min": [22.1],
                    "precipitation_probability_max": [35],
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenMeteoWeatherProvider(client=client)

    result = provider.get_forecast(WeatherRequest(destination="成都"))

    assert result.success is True
    assert result.source == "open-meteo"
    assert result.data_mode is ToolDataMode.REALTIME
    assert result.data["resolved_location"]["name"] == "成都"
    assert "预计多云" in result.data["summary"]


def test_open_meteo_location_not_found_is_not_retryable() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"generationtime_ms": 0.1})
        )
    )
    result = OpenMeteoWeatherProvider(client=client).get_forecast(
        WeatherRequest(destination="不存在的目的地")
    )

    assert result.success is False
    assert result.error_code == "WEATHER_LOCATION_NOT_FOUND"
    assert result.retryable is False


def test_open_meteo_uses_administrative_geocoder_fallback_for_district() -> None:
    requested_queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            return httpx.Response(200, json={})
        if request.url.host == "nominatim.openstreetmap.org":
            requested_queries.append(request.url.params["q"])
            return httpx.Response(
                200,
                json=[
                    {
                        "name": "新津区",
                        "display_name": "新津区, 成都市, 四川省, 中国",
                        "lat": "30.4157345",
                        "lon": "103.8068584",
                        "type": "administrative",
                        "addresstype": "county",
                        "address": {
                            "county": "新津区",
                            "city": "成都市",
                            "state": "四川省",
                            "country": "中国",
                        },
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "timezone": "Asia/Shanghai",
                "current": {"temperature_2m": 30, "weather_code": 0},
                "daily": {
                    "time": ["2026-07-20"],
                    "weather_code": [0],
                    "temperature_2m_max": [35],
                    "temperature_2m_min": [24],
                    "precipitation_probability_max": [10],
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenMeteoWeatherProvider(client=client).get_forecast(
        WeatherRequest(destination="成都新津区")
    )

    assert result.success is True
    assert result.source == "open-meteo+nominatim"
    assert result.data["resolved_location"]["name"] == "新津区"
    assert result.data["resolved_location"]["geocoding_source"] == "nominatim"
    assert requested_queries == ["新津区, 成都, 中国"]


def test_osrm_provider_maps_leg_units_and_ids() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "code": "Ok",
                    "routes": [
                        {
                            "distance": 12600.0,
                            "duration": 2100.0,
                            "legs": [
                                {"distance": 4200.0, "duration": 720.0},
                                {"distance": 8400.0, "duration": 1380.0},
                            ],
                        }
                    ],
                },
            )
        )
    )
    provider = OsrmRouteProvider(client=client)

    result = provider.get_route(
        RouteMatrixRequest(
            points=[
                RoutePoint(point_id="A", name="甲", latitude=30.6, longitude=104.0),
                RoutePoint(point_id="B", name="乙", latitude=30.7, longitude=104.1),
                RoutePoint(point_id="C", name="丙", latitude=30.8, longitude=104.2),
            ]
        )
    )

    assert result.success is True
    assert result.data_mode is ToolDataMode.REALTIME
    assert result.data["route_legs"] == [
        {"from_id": "A", "to_id": "B", "distance_km": 4.2, "duration_minutes": 12},
        {"from_id": "B", "to_id": "C", "distance_km": 8.4, "duration_minutes": 23},
    ]


def test_route_adapter_rejects_missing_coordinates_without_fake_distance() -> None:
    class NeverCalledProvider:
        def get_route(self, request):
            raise AssertionError(f"provider must not be called: {request}")

    registry = ToolRegistry(
        {ToolName.ROUTE_MATRIX: RouteProviderTool(NeverCalledProvider())}
    )
    outcome = ToolExecutor(registry).execute(
        ToolName.ROUTE_MATRIX,
        ToolContext(
            entities=TravelEntities(destination="成都"),
            phase1_research=Phase1Research(
                destination="成都",
                weather_summary="",
                poi_candidates=[
                    POICandidate(
                        poi_id="POI-A",
                        name="景点 A",
                        area="成都",
                        suggested_duration_minutes=120,
                    ),
                    POICandidate(
                        poi_id="POI-B",
                        name="景点 B",
                        area="成都",
                        suggested_duration_minutes=120,
                    ),
                ],
            ),
            candidate_selection=CandidateSelection(selected_poi_ids=["POI-A", "POI-B"]),
        ),
    )

    assert outcome.result.success is True
    assert outcome.result.data_mode is ToolDataMode.FALLBACK
    assert outcome.result.data["route_legs"] == []
    assert outcome.errors[0].error_code == "ROUTE_COORDINATES_MISSING"


def test_route_adapter_accepts_only_provider_verified_coordinates() -> None:
    captured = []

    class RecordingProvider:
        def get_route(self, request):
            captured.append(request)
            return ToolResult(
                success=True,
                source="recording-map",
                data_mode=ToolDataMode.REALTIME,
                data={"route_legs": []},
            )

    tool = RouteProviderTool(RecordingProvider())
    result = tool(
        ToolContext(
            phase1_research=Phase1Research(
                destination="成都",
                weather_summary="",
                poi_candidates=[
                    POICandidate(
                        poi_id="POI-A",
                        name="景点 A",
                        area="成都",
                        suggested_duration_minutes=120,
                        latitude=30.6,
                        longitude=104.0,
                        coordinate_source="poi-provider",
                        coordinates_verified=True,
                    ),
                    POICandidate(
                        poi_id="POI-B",
                        name="景点 B",
                        area="成都",
                        suggested_duration_minutes=120,
                        latitude=30.7,
                        longitude=104.1,
                        coordinate_source="poi-provider",
                        coordinates_verified=True,
                    ),
                ],
            ),
            candidate_selection=CandidateSelection(selected_poi_ids=["POI-A", "POI-B"]),
        )
    )

    assert result.success is True
    assert [point.point_id for point in captured[0].points] == ["POI-A", "POI-B"]


def test_nominatim_resolves_and_caches_provider_verified_poi_coordinates() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path.endswith("/search")
        assert "Chengdu" in request.url.params["q"]
        return httpx.Response(
            200,
            json=[
                {
                    "display_name": "Panda Base, Chengdu, Sichuan, China",
                    "lat": "30.7380",
                    "lon": "104.1410",
                    "address": {"city": "Chengdu", "state": "Sichuan"},
                }
            ],
        )

    provider = NominatimPoiCoordinateProvider(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    request = PoiCoordinateRequest(
        destination="Chengdu",
        pois=[PoiCoordinateQuery(poi_id="POI-PANDA", name="Panda Base")],
    )

    first = provider.resolve_coordinates(request)
    second = provider.resolve_coordinates(request)

    assert first.success is True
    assert first.source == "nominatim-poi"
    assert first.data["resolved"][0]["poi_id"] == "POI-PANDA"
    assert first.data["resolved"][0]["latitude"] == 30.738
    assert second.success is True
    assert calls == 1


def test_coordinate_result_marks_only_resolved_candidates_as_verified() -> None:
    research = Phase1Research(
        destination="Chengdu",
        weather_summary="clear",
        poi_candidates=[
            POICandidate(
                poi_id="POI-A",
                name="Panda Base",
                area="Chengdu",
                suggested_duration_minutes=180,
            ),
            POICandidate(
                poi_id="POI-B",
                name="Unknown Place",
                area="Chengdu",
                suggested_duration_minutes=120,
            ),
        ],
    )
    result = ToolResult(
        success=True,
        source="nominatim-poi",
        data_mode=ToolDataMode.REALTIME,
        data={
            "resolved": [
                {
                    "poi_id": "POI-A",
                    "latitude": 30.738,
                    "longitude": 104.141,
                }
            ]
        },
    )

    enriched = apply_verified_coordinates(research, result)

    assert enriched.poi_candidates[0].coordinates_verified is True
    assert enriched.poi_candidates[0].coordinate_source == "nominatim-poi"
    assert enriched.poi_candidates[1].coordinates_verified is False


def test_live_registry_excludes_agent_reach_even_when_offline_pipeline_is_enabled() -> None:
    settings = replace(
        load_settings(),
        agent_reach_enabled=True,
        xiaohongshu_enabled=True,
    )

    live = build_live_tool_registry(settings)
    offline = build_knowledge_research_registry(settings)

    assert live.names == {
        ToolName.WEATHER,
        ToolName.POI_COORDINATES,
        ToolName.ROUTE_MATRIX,
    }
    assert ToolName.TRAVEL_RESEARCH not in live.names
    assert ToolName.XIAOHONGSHU_RESEARCH not in live.names
    assert ToolName.TRAVEL_RESEARCH in offline.names
    assert ToolName.XIAOHONGSHU_RESEARCH in offline.names


def test_query_presenter_accepts_chinese_date_grounded_by_iso_tool_date() -> None:
    result = ToolResult(
        success=True,
        source="open-meteo",
        data_mode=ToolDataMode.REALTIME,
        data={"daily": [{"date": "2026-07-20"}]},
    )

    LangChainQueryPresenterAgent._validate_grounding(
        "成都7月20日天气晴朗。",
        {ToolName.WEATHER.value: result},
    )


def test_query_presenter_still_rejects_date_absent_from_tool_result() -> None:
    result = ToolResult(
        success=True,
        source="open-meteo",
        data_mode=ToolDataMode.REALTIME,
        data={"daily": [{"date": "2026-07-20"}]},
    )

    with pytest.raises(ValueError, match="ungrounded date"):
        LangChainQueryPresenterAgent._validate_grounding(
            "成都7月31日天气晴朗。",
            {ToolName.WEATHER.value: result},
        )
