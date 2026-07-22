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
    business_backend: str
    java_backend_base_url: str
    java_internal_service_secret: str
    chroma_server_url: str | None = None
    embedding_backend: str = "bge-small-zh-v1.5"
    bge_model_directory: Path = PROJECT_ROOT / ".data/models/bge-small-zh-v1.5"
    bge_auto_download: bool = False
    tool_http_timeout_seconds: float = 10.0
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    open_meteo_geocoding_url: str = "https://geocoding-api.open-meteo.com/v1"
    osrm_base_url: str = "https://router.project-osrm.org"
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "oneclick-trip/0.8 (educational travel agent)"
    agent_reach_enabled: bool = False
    agent_reach_cache_ttl_seconds: float = 300.0
    agent_reach_result_limit: int = 5
    agent_reach_fetch_top: int = 2
    xiaohongshu_enabled: bool = False
    xiaohongshu_result_limit: int = 8
    xiaohongshu_detail_limit: int = 2
    xiaohongshu_detail_delay_seconds: float = 2.2

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
    raw_bge_path = Path(
        os.getenv("BGE_MODEL_DIRECTORY", ".data/models/bge-small-zh-v1.5")
    )
    bge_path = raw_bge_path if raw_bge_path.is_absolute() else PROJECT_ROOT / raw_bge_path
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
        business_backend=os.getenv("BUSINESS_BACKEND", "java").lower(),
        java_backend_base_url=os.getenv(
            "JAVA_BACKEND_BASE_URL", "http://127.0.0.1:8080"
        ).rstrip("/"),
        java_internal_service_secret=os.getenv(
            "AI_INTERNAL_SERVICE_SECRET", "oneclick-trip-internal-dev-secret"
        ),
        chroma_server_url=os.getenv("CHROMA_SERVER_URL") or None,
        embedding_backend=os.getenv(
            "EMBEDDING_BACKEND", "bge-small-zh-v1.5"
        ).lower(),
        bge_model_directory=bge_path,
        bge_auto_download=os.getenv("BGE_AUTO_DOWNLOAD", "false").lower()
        in {"1", "true", "yes", "on"},
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
        agent_reach_enabled=os.getenv("AGENT_REACH_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        agent_reach_cache_ttl_seconds=float(
            os.getenv("AGENT_REACH_CACHE_TTL_SECONDS", "300")
        ),
        agent_reach_result_limit=int(os.getenv("AGENT_REACH_RESULT_LIMIT", "5")),
        agent_reach_fetch_top=int(os.getenv("AGENT_REACH_FETCH_TOP", "2")),
        xiaohongshu_enabled=os.getenv("XIAOHONGSHU_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        xiaohongshu_result_limit=int(os.getenv("XIAOHONGSHU_RESULT_LIMIT", "8")),
        xiaohongshu_detail_limit=int(os.getenv("XIAOHONGSHU_DETAIL_LIMIT", "2")),
        xiaohongshu_detail_delay_seconds=float(
            os.getenv("XIAOHONGSHU_DETAIL_DELAY_SECONDS", "2.2")
        ),
    )
