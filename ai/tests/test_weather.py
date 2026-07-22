import asyncio
import unittest

import httpx
from fastapi import HTTPException

from app.weather import FORECAST_URL, GEOCODING_URL, WeatherService


class WeatherServiceTest(unittest.TestCase):
    def test_city_weather_is_normalized_and_cached(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if str(request.url).startswith(GEOCODING_URL):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "成都",
                                "latitude": 30.67,
                                "longitude": 104.07,
                                "timezone": "Asia/Shanghai",
                                "country": "中国",
                                "admin1": "四川",
                            }
                        ]
                    },
                )
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Shanghai",
                    "current": {
                        "time": "2026-07-15T12:00",
                        "temperature_2m": 28.4,
                        "apparent_temperature": 30.1,
                        "relative_humidity_2m": 75,
                        "precipitation": 0,
                        "weather_code": 2,
                        "wind_speed_10m": 5.2,
                    },
                    "daily": {
                        "time": ["2026-07-15"],
                        "weather_code": [2],
                        "temperature_2m_max": [31.0],
                        "temperature_2m_min": [23.0],
                        "precipitation_probability_max": [40],
                    },
                },
            )

        async def scenario() -> None:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                service = WeatherService(client=client)
                first = await service.get_weather(
                    city="成都", latitude=None, longitude=None, forecast_days=1
                )
                second = await service.get_weather(
                    city="成都", latitude=None, longitude=None, forecast_days=1
                )
                self.assertEqual(first["current"]["weather"], "局部多云")
                self.assertEqual(first["location"]["name"], "成都")
                self.assertFalse(first["cache_hit"])
                self.assertTrue(second["cache_hit"])
                self.assertEqual(len(calls), 3)

        asyncio.run(scenario())

    def test_device_location_requires_coordinates(self) -> None:
        async def scenario() -> None:
            service = WeatherService()
            with self.assertRaises(HTTPException) as raised:
                await service.get_weather(
                    city="DEVICE_CURRENT_CITY",
                    latitude=None,
                    longitude=None,
                    forecast_days=1,
                )
            self.assertEqual(raised.exception.status_code, 400)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
