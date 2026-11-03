from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .context import Label


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

# Web search backends (agentkit-tools `web_search`); all optional.
_SEARCH_KEYS = ("PARALLEL_API_KEY", "BRAVE_API_KEY", "TAVILY_API_KEY")


def find_env_file(start: Path | None = None) -> Path | None:
    """The nearest `.env` in `start` (default: cwd) or any parent directory."""
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / ".env").is_file():
            return d / ".env"
    return None


class Settings(BaseSettings):
    """Secrets from `.env` (never committed), found by walking up from the cwd.

    `.env` wins over process env vars, so a stale shell export cannot shadow the key in `.env`.
    Explicit constructor kwargs still win over both. Only the selected provider's key is required.
    """

    model_config = SettingsConfigDict(env_file=find_env_file(), extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    openai_api_key: SecretStr | None = None
    google_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    fireworks_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    parallel_api_key: SecretStr | None = None
    brave_api_key: SecretStr | None = None
    # The one tenant this deployment serves; every run's PlatformContext.tenant must match it.
    deployment_tenant: Label = Field(
        default="default", validation_alias=AliasChoices("AGENTKIT_TENANT", "deployment_tenant")
    )

    def env_file_used(self) -> Path | None:
        env = self.model_config.get("env_file")
        return Path(env) if isinstance(env, (str, Path)) else None

    def keys_present(self) -> list[str]:
        """Names (never values) of the API keys that are set."""
        names = [*_ENV_VAR.values(), *_SEARCH_KEYS]
        return [n for n in names if (v := getattr(self, n.lower())) and v.get_secret_value()]

    def require_key(self, provider: Provider) -> str:
        key = getattr(self, _ENV_VAR[provider].lower())
        if key is None or not key.get_secret_value():
            raise ConfigError(f"{_ENV_VAR[provider]} is required for provider '{provider}'")
        return str(key.get_secret_value())
