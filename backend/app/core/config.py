from functools import lru_cache

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str = Field(..., min_length=1) 
    gemini_model: str = Field(default="gemini-3.5-flash-lite", min_length=1)
    gemini_api_base_url: HttpUrl = Field(
        default="https://generativelanguage.googleapis.com/v1beta"
    )
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    api_key: str = Field(..., min_length=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 20
    redis_socket_connect_timeout: float = 3.0
    redis_socket_timeout: float = 5.0

    @field_validator("gemini_api_key", "gemini_model", "api_key")
    @classmethod
    def validate_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Configuration value cannot be empty or whitespace")
        return stripped

@lru_cache
def get_settings() -> Settings:
    return Settings()