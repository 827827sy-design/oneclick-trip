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
    )
