from __future__ import annotations

from typing import Any

import httpx

from app.domain.models import ToolDataMode, ToolResult
from app.tools.providers.contracts import RouteMatrixRequest


class OsrmRouteProvider:
    """Sequential route adapter for OSRM-compatible HTTP services."""

    def __init__(
        self,
        *,
        base_url: str = "https://router.project-osrm.org",
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    def get_route(self, request: RouteMatrixRequest) -> ToolResult:
        coordinates = ";".join(
            f"{point.longitude},{point.latitude}" for point in request.points
        )
        url = f"{self._base_url}/route/v1/{request.profile}/{coordinates}"
        try:
            payload = self._get_json(
                url,
                params={"overview": "false", "steps": "false"},
            )
            routes = payload.get("routes") or []
            if payload.get("code") != "Ok" or not routes:
                return self._failure("ROUTE_NOT_FOUND", "未找到可用路线", retryable=False)
            legs = routes[0].get("legs") or []
            route_legs = []
            for index, leg in enumerate(legs):
                if index + 1 >= len(request.points):
                    break
                route_legs.append(
                    {
                        "from_id": request.points[index].point_id,
                        "to_id": request.points[index + 1].point_id,
                        "distance_km": round(float(leg.get("distance", 0)) / 1000, 1),
                        "duration_minutes": max(1, round(float(leg.get("duration", 0)) / 60)),
                    }
                )
            return ToolResult(
                success=True,
                source="osrm",
                data_mode=ToolDataMode.REALTIME,
                confidence=0.9,
                data={
                    "data_mode": ToolDataMode.REALTIME.value,
                    "source": "osrm",
                    "profile": request.profile,
                    "route_legs": route_legs,
                    "total_distance_km": round(float(routes[0].get("distance", 0)) / 1000, 1),
                    "total_duration_minutes": max(
                        1, round(float(routes[0].get("duration", 0)) / 60)
                    ),
                },
            )
        except httpx.TimeoutException:
            return self._failure("ROUTE_TIMEOUT", "路线服务请求超时", retryable=True)
        except httpx.HTTPStatusError as exc:
            retryable = exc.response.status_code == 429 or exc.response.status_code >= 500
            return self._failure(
                f"ROUTE_HTTP_{exc.response.status_code}",
                "路线服务暂时不可用",
                retryable=retryable,
            )
        except (httpx.RequestError, TypeError, ValueError):
            return self._failure("ROUTE_RESPONSE_INVALID", "路线服务返回异常", retryable=True)

    def _get_json(self, url: str, *, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"User-Agent": "oneclick-trip/0.8 (+travel-agent)"}
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
    def _failure(error_code: str, message: str, *, retryable: bool) -> ToolResult:
        return ToolResult(
            success=False,
            source="osrm",
            data_mode=ToolDataMode.REALTIME,
            data={"message": message, "source": "osrm", "data_mode": "REALTIME"},
            error_code=error_code,
            retryable=retryable,
        )
