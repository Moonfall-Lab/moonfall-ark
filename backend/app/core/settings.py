from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import BACKEND_DIR, DEFAULT_SQLITE_DB_PATH, PROJECT_ROOT


class Settings(BaseSettings):
    runtime_host: str = "0.0.0.0"
    runtime_port: int = 8000

    llm_provider: str = "deepseek"

    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    nvidia_base_url: str = "http://localhost:8000/v1"
    nvidia_api_key: str = ""
    nvidia_model: str = ""

    sqlite_db_path: str = "backend/data/moonfall.db"

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def resolved_sqlite_db_path(self) -> Path:
        path = Path(self.sqlite_db_path)
        if path.is_absolute():
            return path
        if path.parts and path.parts[0] == "backend":
            return PROJECT_ROOT / path
        return BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


DB_PATH = settings.resolved_sqlite_db_path if settings.sqlite_db_path else DEFAULT_SQLITE_DB_PATH
