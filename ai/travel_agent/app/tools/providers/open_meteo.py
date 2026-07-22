from __future__ import annotations

from datetime import date, timedelta
import re
from threading import Lock
import time
from typing import Any

import httpx

from app.domain.models import ToolDataMode, ToolResult
from app.tools.providers.contracts import WeatherRequest


WEATHER_LABELS = {
    0: "晴",
    1: "大致晴朗",
    2: "多云",
    3: "阴",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "较强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴冰雹",
}


class OpenMeteoWeatherProvider:
    """Keyless weather adapter backed by Open-Meteo forecast and geocoding APIs."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.open-meteo.com/v1",
        geocoding_url: str = "https://geocoding-api.open-meteo.com/v1",
        nominatim_url: str = "https://nominatim.openstreetmap.org",
        nominatim_user_agent: str = "oneclick-trip/0.8 (educational travel agent)",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._geocoding_url = geocoding_url.rstrip("/")
        self._nominatim_url = nominatim_url.rstrip("/")
        self._nominatim_user_agent = nominatim_user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._nominatim_lock = Lock()
        self._last_nominatim_request = 0.0
        self._location_cache: dict[str, dict[str, Any]] = {}

    def get_forecast(self, request: WeatherRequest) -> ToolResult:
        try:
            place = self._resolve_location(request.destination)
            if place is None:
                return self._failure(
                    "WEATHER_LOCATION_NOT_FOUND",
                    f"未找到目的地：{request.destination}",
                    retryable=False,
                )
            params: dict[str, Any] = {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "timezone": "auto",
                "current": (
                    "temperature_2m,apparent_temperature,weather_code,"
                    "precipitation,wind_speed_10m"
                ),
                "daily": (
                    "weather_code,temperature_2m_max,temperature_2m_min,"
                    "precipitation_probability_max"
                ),
            }
            self._apply_date_range(params, request)
            forecast = self._get_json(f"{self._base_url}/forecast", params=params)
            daily_rows = self._daily_rows(forecast.get("daily") or {})
            current = forecast.get("current") or {}
            summary = self._summary(request.destination, current, daily_rows)
            geocoding_source = place.get("geocoding_source", "open-meteo")
            result_source = (
                "open-meteo"
                if geocoding_source == "open-meteo"
                else "open-meteo+nominatim"
            )
            return ToolResult(
                success=True,
                source=result_source,
                data_mode=ToolDataMode.REALTIME,
                confidence=0.95,
                data={
                    "data_mode": ToolDataMode.REALTIME.value,
                    "source": result_source,
                    "destination": request.destination,
                    "resolved_location": {
                        "name": place.get("name"),
                        "admin1": place.get("admin1"),
                        "country": place.get("country"),
                        "latitude": place["latitude"],
                        "longitude": place["longitude"],
                        "timezone": forecast.get("timezone"),
                        "geocoding_source": geocoding_source,
                    },
                    "current": current,
                    "units": forecast.get("current_units") or {},
                    "daily": daily_rows,
                    "summary": summary,
                },
            )
        except httpx.TimeoutException:
            return self._failure("WEATHER_TIMEOUT", "天气服务请求超时", retryable=True)
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            return self._failure(
                f"WEATHER_HTTP_{exc.response.status_code}",
                "天气服务暂时不可用",
                retryable=retryable,
            )
        except (httpx.RequestError, KeyError, TypeError, ValueError):
            return self._failure(
                "WEATHER_RESPONSE_INVALID",
                "天气服务返回异常",
                retryable=True,
            )

    def _resolve_location(self, destination: str) -> dict[str, Any] | None:
        cached = self._location_cache.get(destination)
        if cached is not None:
            return cached
        location = self._get_json(
            f"{self._geocoding_url}/search",
            params={
                "name": destination,
                "count": 1,
                "language": "zh",
                "format": "json",
            },
        )
        if isinstance(location, dict) and location.get("results"):
            place = dict(location["results"][0])
            place["geocoding_source"] = "open-meteo"
            self._location_cache[destination] = place
            return place
        place = self._resolve_with_nominatim(destination)
        if place is not None:
            self._location_cache[destination] = place
        return place

    def _resolve_with_nominatim(self, destination: str) -> dict[str, Any] | None:
        for query in _administrative_queries(destination):
            with self._nominatim_lock:
                if self._client is None:
                    wait_seconds = 1.0 - (time.monotonic() - self._last_nominatim_request)
                    if wait_seconds > 0:
                        time.sleep(wait_seconds)
                payload = self._get_json(
                    f"{self._nominatim_url}/search",
                    params={
                        "q": query,
                        "format": "jsonv2",
                        "limit": 3,
                        "countrycodes": "cn",
                        "addressdetails": 1,
                    },
                    headers={"User-Agent": self._nominatim_user_agent},
                )
                self._last_nominatim_request = time.monotonic()
            if not isinstance(payload, list):
                continue
            administrative = next(
                (
                    item
                    for item in payload
                    if item.get("type") == "administrative"
                    or item.get("addresstype")
                    in {"city", "county", "district", "state", "town", "village"}
                ),
                None,
            )
            if administrative is None:
                continue
            address = administrative.get("address") or {}
            return {
                "name": (
                    address.get("city_district")
                    or address.get("county")
                    or address.get("city")
                    or administrative.get("name")
                    or destination
                ),
                "admin1": address.get("state"),
                "country": address.get("country", "中国"),
                "latitude": float(administrative["lat"]),
                "longitude": float(administrative["lon"]),
                "geocoding_source": "nominatim",
            }
        return None

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self._client is not None:
            response = self._client.get(
                url, params=params, headers=headers, timeout=self._timeout
            )
            response.raise_for_status()
            return response.json()
        with httpx.Client(timeout=self._timeout, headers=headers) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _apply_date_range(params: dict[str, Any], request: WeatherRequest) -> None:
        today = date.today()
        latest = today + timedelta(days=15)
        if request.start_date and today <= request.start_date <= latest:
            end_date = request.end_date or request.start_date
            params["start_date"] = request.start_date.isoformat()
            params["end_date"] = min(end_date, latest).isoformat()
        else:
            params["forecast_days"] = 7

    @staticmethod
    def _daily_rows(daily: dict[str, Any]) -> list[dict[str, Any]]:
        times = daily.get("time") or []
        rows: list[dict[str, Any]] = []
        for index, day in enumerate(times):
            code = _at(daily.get("weather_code"), index)
            rows.append(
                {
                    "date": day,
                    "weather": WEATHER_LABELS.get(code, "天气待确认"),
                    "weather_code": code,
                    "temperature_max": _at(daily.get("temperature_2m_max"), index),
                    "temperature_min": _at(daily.get("temperature_2m_min"), index),
                    "precipitation_probability_max": _at(
                        daily.get("precipitation_probability_max"), index
                    ),
                }
            )
        return rows

    @staticmethod
    def _summary(
        destination: str,
        current: dict[str, Any],
        daily_rows: list[dict[str, Any]],
    ) -> str:
        if daily_rows:
            day = daily_rows[0]
            return (
                f"{destination}{day['date']}预计{day['weather']}，"
                f"{day['temperature_min']}-{day['temperature_max']} 摄氏度，"
                f"最高降雨概率 {day['precipitation_probability_max']}%。"
            )
        code = current.get("weather_code")
        return (
            f"{destination}当前{WEATHER_LABELS.get(code, '天气待确认')}，"
            f"气温 {current.get('temperature_2m', '未知')} 摄氏度。"
        )

    @staticmethod
    def _failure(error_code: str, message: str, *, retryable: bool) -> ToolResult:
        return ToolResult(
            success=False,
            source="open-meteo",
            data_mode=ToolDataMode.REALTIME,
            data={"message": message, "source": "open-meteo", "data_mode": "REALTIME"},
            error_code=error_code,
            retryable=retryable,
        )


def _at(values: Any, index: int) -> Any:
    return values[index] if isinstance(values, list) and index < len(values) else None


def _administrative_queries(destination: str) -> list[str]:
    cleaned = re.sub(r"\s+", "", destination)
    queries: list[str] = []
    if cleaned.endswith(("区", "县", "旗")):
        suffix = cleaned[-1]
        stem = cleaned[:-1]
        for width in range(2, min(4, len(stem)) + 1):
            child = f"{stem[-width:]}{suffix}"
            parent = stem[:-width]
            query = f"{child}, {parent}, 中国" if parent else f"{child}, 中国"
            if query not in queries:
                queries.append(query)
    full_query = f"{cleaned}, 中国"
    if full_query not in queries:
        queries.append(full_query)
    return queries
