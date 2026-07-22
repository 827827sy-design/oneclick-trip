from __future__ import annotations

from threading import Lock
import time
from typing import Any

import httpx

from app.domain.models import ToolDataMode, ToolResult
from app.tools.providers.contracts import PoiCoordinateRequest


class NominatimPoiCoordinateProvider:
    """Resolve named POIs before OSRM is allowed to calculate a route."""

    def __init__(
        self,
        *,
        base_url: str = "https://nominatim.openstreetmap.org",
        user_agent: str = "oneclick-trip/0.8 (educational travel agent)",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._timeout = timeout_seconds
        self._client = client
        self._lock = Lock()
        self._last_request = 0.0
        self._cache: dict[str, dict[str, Any] | None] = {}

    def resolve_coordinates(self, request: PoiCoordinateRequest) -> ToolResult:
        resolved = []
        unresolved = []
        try:
            for poi in request.pois:
                cache_key = f"{request.destination}::{poi.name}".casefold()
                if cache_key not in self._cache:
                    self._cache[cache_key] = self._resolve_one(
                        poi.name,
                        request.destination,
                    )
                place = self._cache[cache_key]
                if place is None:
                    unresolved.append({"poi_id": poi.poi_id, "name": poi.name})
                    continue
                resolved.append(
                    {
                        "poi_id": poi.poi_id,
                        "name": poi.name,
                        "latitude": float(place["lat"]),
                        "longitude": float(place["lon"]),
                        "display_name": place.get("display_name"),
                    }
                )
        except httpx.TimeoutException:
            return self._failure("POI_GEOCODING_TIMEOUT", "景点定位超时", True)
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            return self._failure(
                f"POI_GEOCODING_HTTP_{exc.response.status_code}",
                "景点定位服务暂时不可用",
                retryable,
            )
        except (httpx.RequestError, KeyError, TypeError, ValueError):
            return self._failure(
                "POI_GEOCODING_RESPONSE_INVALID",
                "景点定位服务返回异常",
                True,
            )

        if not resolved:
            return self._failure(
                "POI_COORDINATES_NOT_FOUND",
                "没有找到可验证的景点坐标",
                False,
                unresolved=unresolved,
            )
        return ToolResult(
            success=True,
            source="nominatim-poi",
            data_mode=ToolDataMode.REALTIME,
            confidence=0.86,
            data={
                "data_mode": ToolDataMode.REALTIME.value,
                "source": "nominatim-poi",
                "resolved": resolved,
                "unresolved": unresolved,
                "resolved_count": len(resolved),
                "requested_count": len(request.pois),
                "partial": bool(unresolved),
            },
        )

    def _resolve_one(self, name: str, destination: str) -> dict[str, Any] | None:
        with self._lock:
            if self._client is None:
                wait_seconds = 1.0 - (time.monotonic() - self._last_request)
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
            payload = self._get_json(
                params={
                    "q": f"{name}, {destination}, 中国",
                    "format": "jsonv2",
                    "limit": 3,
                    "countrycodes": "cn",
                    "addressdetails": 1,
                }
            )
            self._last_request = time.monotonic()
        if not isinstance(payload, list):
            return None
        return next(
            (
                item
                for item in payload
                if item.get("lat") is not None
                and item.get("lon") is not None
                and _matches_destination(item, destination)
            ),
            None,
        )

    def _get_json(self, *, params: dict[str, Any]) -> Any:
        headers = {"User-Agent": self._user_agent}
        if self._client is not None:
            response = self._client.get(
                f"{self._base_url}/search",
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()
        with httpx.Client(timeout=self._timeout, headers=headers) as client:
            response = client.get(f"{self._base_url}/search", params=params)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _failure(
        error_code: str,
        message: str,
        retryable: bool,
        *,
        unresolved: list[dict[str, str]] | None = None,
    ) -> ToolResult:
        return ToolResult(
            success=False,
            source="nominatim-poi",
            data_mode=ToolDataMode.REALTIME,
            data={"message": message, "unresolved": unresolved or []},
            error_code=error_code,
            retryable=retryable,
        )


def _matches_destination(item: dict[str, Any], destination: str) -> bool:
    haystack = " ".join(
        str(value)
        for value in (
            item.get("display_name"),
            *(item.get("address") or {}).values(),
        )
        if value
    )
    normalized = destination.removesuffix("市").removesuffix("区").strip()
    return not normalized or normalized in haystack
