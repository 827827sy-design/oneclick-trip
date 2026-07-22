from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_LABELS = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    56: "轻微冻雨",
    57: "强冻雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


@dataclass(frozen=True)
class CachedWeather:
    expires_at: float
    value: dict[str, Any]


class WeatherService:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: int = 600,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, CachedWeather] = {}
        self._cache_lock = asyncio.Lock()

    async def get_weather(
        self,
        *,
        city: str | None,
        latitude: float | None,
        longitude: float | None,
        forecast_days: int,
    ) -> dict[str, Any]:
        location = await self._resolve_location(city, latitude, longitude)
        cache_key = f"{location['latitude']:.4f}:{location['longitude']:.4f}:{forecast_days}"

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and cached.expires_at > time.monotonic():
                return {**cached.value, "cache_hit": True}

        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "current": ",".join(
                [
                    "temperature_2m",
                    "apparent_temperature",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                    "wind_speed_10m",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_probability_max",
                ]
            ),
            "timezone": "auto",
            "forecast_days": forecast_days,
        }
        payload = await self._get_json(FORECAST_URL, params)
        result = self._normalize_weather(location, payload)

        async with self._cache_lock:
            self._cache[cache_key] = CachedWeather(
                expires_at=time.monotonic() + self._cache_ttl_seconds,
                value=result,
            )
        return {**result, "cache_hit": False}

    async def _resolve_location(
        self,
        city: str | None,
        latitude: float | None,
        longitude: float | None,
    ) -> dict[str, Any]:
        if latitude is not None and longitude is not None:
            return {
                "name": city or "当前位置",
                "latitude": latitude,
                "longitude": longitude,
                "timezone": "auto",
                "source": "device_coordinates",
            }
        if not city or city == "DEVICE_CURRENT_CITY":
            raise HTTPException(
                status_code=400,
                detail="请传入城市名称，或由小程序定位后传入 latitude 和 longitude。",
            )

        payload = await self._get_json(
            GEOCODING_URL,
            {
                "name": city,
                "count": 1,
                "language": "zh",
                "format": "json",
                "countryCode": "CN",
            },
        )
        results = payload.get("results") or []
        if not results:
            raise HTTPException(status_code=404, detail=f"没有找到城市：{city}")
        match = results[0]
        return {
            "name": match.get("name", city),
            "admin1": match.get("admin1"),
            "country": match.get("country"),
            "latitude": match["latitude"],
            "longitude": match["longitude"],
            "timezone": match.get("timezone", "auto"),
            "source": "open_meteo_geocoding",
        }

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = await self._client.get(url, params=params)
            else:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(status_code=502, detail=f"天气数据源请求失败：{exc}") from exc

    @staticmethod
    def _normalize_weather(location: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []
        days = []
        for index, date in enumerate(dates):
            code = _at(daily.get("weather_code"), index)
            days.append(
                {
                    "date": date,
                    "weather_code": code,
                    "weather": WEATHER_LABELS.get(code, "未知"),
                    "temperature_max": _at(daily.get("temperature_2m_max"), index),
                    "temperature_min": _at(daily.get("temperature_2m_min"), index),
                    "precipitation_probability_max": _at(
                        daily.get("precipitation_probability_max"), index
                    ),
                }
            )

        current_code = current.get("weather_code")
        return {
            "status": "SUCCESS",
            "location": location,
            "current": {
                "observed_at": current.get("time"),
                "temperature": current.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "relative_humidity": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "wind_speed": current.get("wind_speed_10m"),
                "weather_code": current_code,
                "weather": WEATHER_LABELS.get(current_code, "未知"),
            },
            "daily": days,
            "timezone": payload.get("timezone"),
            "source": {
                "provider": "Open-Meteo",
                "forecast_url": FORECAST_URL,
                "geocoding_url": GEOCODING_URL,
                "retrieved_at": current.get("time"),
            },
        }


def _at(values: list[Any] | None, index: int) -> Any:
    if not values or index >= len(values):
        return None
    return values[index]
