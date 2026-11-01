"""agentkit-core: settings and model registry."""

from .factory import get_model
from .registry import TIERS, ModelRegistry, ModelSpec
from .settings import ConfigError, Provider, Settings

__all__ = [
    "TIERS",
    "ConfigError",
    "ModelRegistry",
    "ModelSpec",
    "Provider",
    "Settings",
    "get_model",
]
