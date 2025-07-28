from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    """Centralised application configuration.

    All runtime options (env vars, CLI flags, secrets) are defined here so the
    rest of the codebase can simply do `from src.config import get_settings`
    and retrieve a cached, validated instance.
    """

    # ---------------------------------------------------------------------
    # Core runtime settings
    # ---------------------------------------------------------------------
    app_env: str = Field("duplo", alias="APP_ENV", description="Running environment: local / staging / duplo / prod …")
    log_level: str = Field("INFO", alias="LOG_LEVEL", description="Application log level (DEBUG, INFO …)")
    log_format: str = Field("console", alias="LOG_FORMAT", description="pretty console vs json")

    # ------------------------------------------------------------------
    # Server
    # ------------------------------------------------------------------
    port: int = Field(8000, alias="PORT", description="FastAPI / Uvicorn port to bind to")
    uvicorn_log_level: str = Field("info", alias="UVICORN_LOG_LEVEL", description="Log level that uvicorn should emit")

    # ------------------------------------------------------------------
    # AWS credentials / region
    # ------------------------------------------------------------------
    aws_region: str = Field("us-east-1", alias="AWS_REGION")
    aws_access_key_id: Optional[str] = Field(None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: Optional[str] = Field(None, alias="AWS_SESSION_TOKEN")

    # ------------------------------------------------------------------
    # Future: Bedrock / OpenAI etc.
    # ------------------------------------------------------------------
    bedrock_model_id: str = Field(
        "anthropic.claude-3-5-sonnet-20240620-v1:0",
        alias="BEDROCK_MODEL_ID",
        description="Default model id used by agents that talk to Bedrock",
    )

    class Config:
        case_sensitive = False
        env_file = Path(__file__).resolve().parent.parent / ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"

    # ----------------------- Validators / hooks ------------------------
    @validator("app_env")
    def _validate_app_env(cls, v: str) -> str:  # noqa: D401, N805
        allowed = {"local", "duplo", "staging", "prod"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}, got '{v}'")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:  # noqa: D401
    """Return a singleton Settings instance (cached)."""

    return Settings() 