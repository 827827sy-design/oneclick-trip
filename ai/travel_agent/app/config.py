from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    infra_mode: str
    mysql_dsn: str | None
    redis_url: str | None
    chroma_persist_directory: Path
    chroma_collection: str
    deepseek_api_key: str | None
    deepseek_base_url: str
    deepseek_flash_model: str
    deepseek_pro_model: str
    tool_http_timeout_seconds: float = 10.0
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    open_meteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1"
    osrm_base_url: str = "https://router.project-osrm.org"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "oneclick-trip/0.8 (educational travel agent)"

    @property
    def use_external_infrastructure(self) -> bool:
        return self.infra_mode in {"auto", "external"}

    @property
    def require_external_infrastructure(self) -> bool:
        return self.infra_mode == "external"


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)
    raw_chroma_path = Path(os.getenv("CHROMA_PERSIST_DIRECTORY", ".data/chroma"))
    chroma_path = raw_chroma_path if raw_chroma_path.is_absolute() else PROJECT_ROOT / raw_chroma_path
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        infra_mode=os.getenv("INFRA_MODE", "memory").lower(),
        mysql_dsn=os.getenv("MYSQL_DSN"),
        redis_url=os.getenv("REDIS_URL"),
        chroma_persist_directory=chroma_path,
        chroma_collection=os.getenv("CHROMA_COLLECTION", "travel_knowledge"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        deepseek_flash_model=os.getenv("DEEPSEEK_FLASH_MODEL", "deepseek-v4-flash"),
        deepseek_pro_model=os.getenv("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro"),
        tool_http_timeout_seconds=float(os.getenv("TOOL_HTTP_TIMEOUT_SECONDS", "10")),
        open_meteo_base_url=os.getenv(
            "OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1"
        ).rstrip("/"),
        open_meteo_geocoding_url=os.getenv(
            "OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1"
        ).rstrip("/"),
        osrm_base_url=os.getenv(
            "OSRM_BASE_URL", "https://router.project-osrm.org"
        ).rstrip("/"),
        nominatim_base_url=os.getenv(
            "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
        ).rstrip("/"),
        nominatim_user_agent=os.getenv(
            "NOMINATIM_USER_AGENT",
            "oneclick-trip/0.8 (educational travel agent)",
        ),
    )
