from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    gemini_api_key: str = Field(..., min_length=1) 
    gemini_model: str = Field(default="gemini-3.5-flash-lite", min_length=1)
    gemini_api_base_url: HttpUrl = Field(
        default="https://generativelanguage.googleapis.com/v1beta"
    )
    llm_timeout_seconds: float = Field(default=30.0, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("gemini_api_key", "gemini_model")
    @classmethod
    def validate_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Configuration value cannot be empty or whitespace")
        return stripped

@lru_cache
def get_settings() -> Settings:
    return Settings()