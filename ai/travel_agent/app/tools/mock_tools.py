from __future__ import annotations

from decimal import Decimal

from app.domain.models import (
    HotelAreaCandidate,
    POICandidate,
    ToolName,
    ToolResult,
    TransportCandidate,
)
from app.tools.contracts import ToolContext
from app.tools.registry import ToolRegistry


def weather_tool(context: ToolContext) -> ToolResult:
    destination = context.entities.destination or "目的地"
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "destination": destination,
            "summary": f"{destination}预计多云，18-27 摄氏度，降雨概率 30%。",
            "source": "mock-weather-provider",
        },
    )


def hotel_search_tool(context: ToolContext) -> ToolResult:
    destination = context.entities.destination or "目的地"
    if destination == "成都":
        areas = [
            HotelAreaCandidate(
                area_id="AREA-CHUNXI",
                name="春熙路商圈",
                reason="地铁换乘方便，餐饮选择丰富，适合第一次到成都。",
                nightly_price_hint=Decimal("420"),
            ),
            HotelAreaCandidate(
                area_id="AREA-KUANZHAI",
                name="宽窄巷子周边",
                reason="靠近历史文化景点，步行体验好，夜间相对从容。",
                nightly_price_hint=Decimal("360"),
            ),
        ]
    else:
        areas = [
            HotelAreaCandidate(
                area_id="AREA-CENTER",
                name=f"{destination}市中心",
                reason="公共交通和餐饮较集中。",
                nightly_price_hint=Decimal("380"),
            )
        ]
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "areas": [area.model_dump(mode="json") for area in areas],
            "source": "mock-hotel-provider",
        },
    )


def train_search_tool(context: ToolContext) -> ToolResult:
    entities = context.entities
    if not entities.origin or not entities.destination:
        return ToolResult(
            success=False,
            data={"message": "火车查询缺少出发地或目的地"},
            error_code="TRANSPORT_SLOTS_MISSING",
            retryable=False,
        )
    option = TransportCandidate(
        option_id="TRAIN-MOCK-001",
        mode="train",
        name=f"{entities.origin}至{entities.destination}高铁方案",
        duration_minutes=420,
        price=Decimal("520"),
    )
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "options": [option.model_dump(mode="json")],
            "source": "mock-train-provider",
        },
    )


def flight_search_tool(context: ToolContext) -> ToolResult:
    entities = context.entities
    if not entities.origin or not entities.destination:
        return ToolResult(
            success=False,
            data={"message": "航班查询缺少出发地或目的地"},
            error_code="TRANSPORT_SLOTS_MISSING",
            retryable=False,
        )
    option = TransportCandidate(
        option_id="FLIGHT-MOCK-001",
        mode="flight",
        name=f"{entities.origin}至{entities.destination}航班方案",
        duration_minutes=180,
        price=Decimal("850"),
    )
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "options": [option.model_dump(mode="json")],
            "source": "mock-flight-provider",
        },
    )


def poi_search_tool(context: ToolContext) -> ToolResult:
    destination = context.entities.destination or "目的地"
    pois = _chengdu_pois() if destination == "成都" else _generic_pois(destination)
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "candidates": [poi.model_dump(mode="json") for poi in pois],
            "source": "mock-poi-rag",
        },
    )


def route_matrix_tool(context: ToolContext) -> ToolResult:
    selected_ids = _selected_poi_ids(context)
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "route_legs": [
                {
                    "from_id": start,
                    "to_id": end,
                    "distance_km": round(3.2 + index * 1.4, 1),
                    "duration_minutes": 20 + index * 5,
                }
                for index, (start, end) in enumerate(
                    zip(selected_ids, selected_ids[1:]),
                    start=1,
                )
            ],
            "source": "mock-map-provider",
        },
    )


def opening_hours_tool(context: ToolContext) -> ToolResult:
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "opening_hours": [
                {"poi_id": poi_id, "opening_hours": _mock_opening_hours(poi_id)}
                for poi_id in _selected_poi_ids(context)
            ],
            "source": "mock-poi-provider",
        },
    )


def ticket_tool(context: ToolContext) -> ToolResult:
    price_by_id = {
        poi.poi_id: poi.ticket_price
        for poi in (context.phase1_research.poi_candidates if context.phase1_research else [])
    }
    return ToolResult(
        success=True,
        data={
            "data_mode": "MOCK",
            "tickets": [
                {
                    "poi_id": poi_id,
                    "ticket_option_id": f"TICKET-{poi_id.removeprefix('POI-')}",
                    "ticket_price": str(price_by_id.get(poi_id, Decimal("0"))),
                    "available": True,
                }
                for poi_id in _selected_poi_ids(context)
            ],
            "source": "mock-ticket-provider",
        },
    )


def build_mock_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        {
            ToolName.WEATHER: weather_tool,
            ToolName.HOTEL_SEARCH: hotel_search_tool,
            ToolName.TRAIN_SEARCH: train_search_tool,
            ToolName.FLIGHT_SEARCH: flight_search_tool,
            ToolName.POI_SEARCH: poi_search_tool,
            ToolName.ROUTE_MATRIX: route_matrix_tool,
            ToolName.OPENING_HOURS: opening_hours_tool,
            ToolName.TICKET: ticket_tool,
        }
    )


def build_allowed_demo_registry() -> ToolRegistry:
    """Expose only demo interfaces permitted in the active application graph."""
    return ToolRegistry({ToolName.WEATHER: weather_tool})


def _selected_poi_ids(context: ToolContext) -> list[str]:
    return (
        context.candidate_selection.selected_poi_ids
        if context.candidate_selection
        else []
    )


def _chengdu_pois() -> list[POICandidate]:
    return [
        POICandidate(
            poi_id="POI-PANDA",
            name="成都大熊猫繁育研究基地",
            area="成华区",
            tags=["自然景观", "亲子", "拍照"],
            suggested_duration_minutes=240,
            ticket_price=Decimal("55"),
        ),
        POICandidate(
            poi_id="POI-DU",
            name="杜甫草堂",
            area="青羊区",
            tags=["历史文化", "园林"],
            suggested_duration_minutes=150,
            ticket_price=Decimal("50"),
        ),
        POICandidate(
            poi_id="POI-KUANZHAI",
            name="宽窄巷子",
            area="青羊区",
            tags=["美食", "历史文化", "街区"],
            suggested_duration_minutes=120,
        ),
        POICandidate(
            poi_id="POI-JINLI",
            name="锦里古街",
            area="武侯区",
            tags=["美食", "历史文化", "夜生活"],
            suggested_duration_minutes=120,
        ),
        POICandidate(
            poi_id="POI-WUHOU",
            name="武侯祠",
            area="武侯区",
            tags=["历史文化"],
            suggested_duration_minutes=150,
            ticket_price=Decimal("50"),
        ),
        POICandidate(
            poi_id="POI-CHUNXI",
            name="春熙路与太古里",
            area="锦江区",
            tags=["购物", "美食", "夜生活"],
            suggested_duration_minutes=150,
        ),
    ]


def _generic_pois(destination: str) -> list[POICandidate]:
    return [
        POICandidate(
            poi_id="POI-LANDMARK",
            name=f"{destination}代表景点",
            area="中心城区",
            tags=["城市地标", "拍照"],
            suggested_duration_minutes=180,
            ticket_price=Decimal("60"),
        ),
        POICandidate(
            poi_id="POI-MUSEUM",
            name=f"{destination}博物馆",
            area="中心城区",
            tags=["历史文化"],
            suggested_duration_minutes=150,
        ),
        POICandidate(
            poi_id="POI-FOOD-STREET",
            name=f"{destination}特色美食街",
            area="中心城区",
            tags=["美食", "夜生活"],
            suggested_duration_minutes=120,
        ),
        POICandidate(
            poi_id="POI-NATURE",
            name=f"{destination}自然风景区",
            area="近郊",
            tags=["自然景观", "徒步", "拍照"],
            suggested_duration_minutes=240,
            ticket_price=Decimal("80"),
        ),
        POICandidate(
            poi_id="POI-OLD-TOWN",
            name=f"{destination}历史街区",
            area="老城区",
            tags=["历史文化", "街区", "美食"],
            suggested_duration_minutes=180,
            ticket_price=Decimal("30"),
        ),
        POICandidate(
            poi_id="POI-CITY-PARK",
            name=f"{destination}城市公园",
            area="中心城区",
            tags=["自然景观", "轻松", "亲子"],
            suggested_duration_minutes=150,
        ),
    ]


def _mock_opening_hours(poi_id: str) -> str:
    if "FOOD" in poi_id:
        return "09:00-22:00"
    if "NATURE" in poi_id:
        return "08:00-19:00"
    if "PARK" in poi_id:
        return "06:00-22:00"
    return "09:00-18:00"
