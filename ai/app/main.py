from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.weather import WeatherService


app = FastAPI(
    title="OneClick Trip AI Tools",
    description="Real-data tool adapters used by Dify and LangGraph.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

weather_service = WeatherService()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "oneclick-trip-ai"}


@app.get("/tools/weather")
async def get_weather(
    city: str | None = Query(default=None, min_length=2, description="Chinese city name"),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    forecast_days: int = Query(default=4, ge=1, le=7),
) -> dict:
    """Return real current conditions and a daily forecast.

    The mini-program should send latitude/longitude after location permission.
    Dify demos can pass a city name such as Chengdu in Chinese.
    """
    return await weather_service.get_weather(
        city=city,
        latitude=latitude,
        longitude=longitude,
        forecast_days=forecast_days,
    )
