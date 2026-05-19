"""Load application settings from the environment."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings (LLM, paths, HTTP API)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["groq", "openai"] = Field(
        default="groq",
        validation_alias="LLM_PROVIDER",
        description="LLM provider: groq (default) or openai",
    )
    groq_api_key: str = Field(
        default="",
        validation_alias="GROQ_API_KEY",
        description="Groq API key (console.groq.com)",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias="GROQ_MODEL",
        description="Groq model id",
    )
    openai_api_key: str = Field(
        default="",
        validation_alias="OPENAI_API_KEY",
        description="OpenAI API key (when LLM_PROVIDER=openai)",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias="OPENAI_MODEL",
        description="OpenAI model name",
    )
    emails_dir: Path = Field(
        default=PROJECT_ROOT / "emails",
        validation_alias="EMAILS_DIR",
        description="Directory of fake `.txt` emails",
    )
    api_host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    api_port: int = Field(default=8000, validation_alias="API_PORT")
    cors_origins: str = Field(
        default="http://localhost:8501,http://127.0.0.1:8501",
        validation_alias="CORS_ORIGINS",
        description="Comma-separated CORS origins",
    )
    llm_max_retries: int = Field(default=3, validation_alias="LLM_MAX_RETRIES")
    llm_timeout_seconds: float = Field(
        default=120.0,
        validation_alias="LLM_TIMEOUT_SECONDS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""

    return Settings()


def cors_origins_list() -> list[str]:
    """Parse CORS origins into a clean list."""

    raw = get_settings().cors_origins
    return [origin.strip() for origin in raw.split(",") if origin.strip()]
