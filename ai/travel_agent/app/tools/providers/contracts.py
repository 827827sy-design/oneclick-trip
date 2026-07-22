from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import Field

from app.domain.models import DomainModel, ToolResult


class WeatherRequest(DomainModel):
    destination: str
    start_date: date | None = None
    end_date: date | None = None


class RoutePoint(DomainModel):
    point_id: str
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RouteMatrixRequest(DomainModel):
    points: list[RoutePoint] = Field(min_length=2)
    profile: str = "driving"


class PoiCoordinateQuery(DomainModel):
    poi_id: str
    name: str


class PoiCoordinateRequest(DomainModel):
    destination: str
    pois: list[PoiCoordinateQuery] = Field(min_length=1, max_length=12)


class HotelSearchRequest(DomainModel):
    destination: str
    check_in: date | None = None
    check_out: date | None = None
    people: int = Field(default=1, ge=1)
    max_nightly_price: Decimal | None = Field(default=None, ge=0)


class TransportSearchRequest(DomainModel):
    origin: str
    destination: str
    departure_date: date | None = None
    people: int = Field(default=1, ge=1)


class TicketSearchRequest(DomainModel):
    poi_ids: list[str]
    visit_date: date | None = None
    people: int = Field(default=1, ge=1)


class WeatherProvider(Protocol):
    def get_forecast(self, request: WeatherRequest) -> ToolResult: ...


class RouteProvider(Protocol):
    def get_route(self, request: RouteMatrixRequest) -> ToolResult: ...


class PoiCoordinateProvider(Protocol):
    def resolve_coordinates(self, request: PoiCoordinateRequest) -> ToolResult: ...


class HotelProvider(Protocol):
    def search_hotels(self, request: HotelSearchRequest) -> ToolResult: ...


class TrainProvider(Protocol):
    def search_trains(self, request: TransportSearchRequest) -> ToolResult: ...


class FlightProvider(Protocol):
    def search_flights(self, request: TransportSearchRequest) -> ToolResult: ...


class TicketProvider(Protocol):
    def search_tickets(self, request: TicketSearchRequest) -> ToolResult: ...
