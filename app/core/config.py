"""Application configuration.

Every value is read from environment variables (or a local ``.env`` file).
No secret ever lives in the source tree — see ``.env.example`` for the contract.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- runtime -------------------------------------------------------
    app_name: str = "ESCAPE"
    environment: Literal["local", "staging", "production"] = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_json: bool = False
    cors_origins: str = ""

    # ---- Tutu MCP ------------------------------------------------------
    mcp_url: str = "https://mcp.tutu.ru/mcp"
    mcp_enabled: bool = True
    mcp_timeout_s: float = 20.0
    mcp_connect_timeout_s: float = 6.0
    mcp_retries: int = 2
    mcp_backoff_s: float = 0.6
    mcp_auth_header: str = ""  # e.g. "Bearer ..." if Tutu ever requires it
    mcp_protocol_version: str = "2025-06-18"
    mcp_tool_map: str = ""  # optional JSON override, see docs/mcp.md
    mcp_max_parallel: int = 4

    # ---- LLM (optional) ------------------------------------------------
    # LLM_ENABLED=true by default: without a real LLM_API_KEY the client is
    # still inert (see `llm_ready`), so this only matters once you paste a key.
    llm_enabled: bool = True
    llm_provider: Literal["openai", "anthropic"] = "openai"
    # Groq's free tier speaks the OpenAI Chat Completions API — get a key at
    # https://console.groq.com/keys (no credit card). Swap to Gemini's free
    # tier by setting LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
    # and LLM_MODEL=gemini-2.0-flash, key from https://aistudio.google.com/apikey.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_key: str = ""
    llm_timeout_s: float = 25.0
    llm_max_tokens: int = 1600
    llm_temperature: float = 0.5

    # ---- Email ---------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "ESCAPE <no-reply@escape.local>"
    smtp_starttls: bool = True
    smtp_timeout_s: float = 15.0
    email_outbox_dir: str = "var/outbox"

    # ---- Product behaviour ---------------------------------------------
    demo_mode: bool = False
    default_origin: str = "Москва"
    currency: str = "RUB"
    escape_ttl_minutes: int = 180
    max_stored_escapes: int = 200

    @field_validator("log_level")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list (empty list = same-origin only)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_ready(self) -> bool:
        """True when the LLM layer is switched on *and* usable."""
        return bool(self.llm_enabled and self.llm_api_key)

    @property
    def smtp_ready(self) -> bool:
        """True when real SMTP credentials are present."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
