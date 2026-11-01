from __future__ import annotations

from enum import StrEnum

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(ValueError):
    """Bad or incomplete platform configuration."""


class Provider(StrEnum):
    OPENAI = "openai"
    GOOGLE = "google_genai"
    ANTHROPIC = "anthropic"
    FIREWORKS = "fireworks"


_ENV_VAR = {
    Provider.OPENAI: "OPENAI_API_KEY",
    Provider.GOOGLE: "GOOGLE_API_KEY",
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.FIREWORKS: "FIREWORKS_API_KEY",
}


class Settings(BaseSettings):
    """Secrets from env / .env (never committed). Only the selected provider's key is required."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    fireworks_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

    def require_key(self, provider: Provider) -> str:
        key = getattr(self, _ENV_VAR[provider].lower())
        if key is None or not key.get_secret_value():
            raise ConfigError(f"{_ENV_VAR[provider]} is required for provider '{provider}'")
        return str(key.get_secret_value())
