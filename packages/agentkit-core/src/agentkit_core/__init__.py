"""agentkit-core: settings and model registry."""

from .build_context import BuildContext
from .factory import get_model
from .registry import TIERS, ModelRegistry, ModelSpec
from .settings import ConfigError, Provider, Settings

__all__ = [
    "TIERS",
    "BuildContext",
    "ConfigError",
    "ModelRegistry",
    "ModelSpec",
    "Provider",
    "Settings",
    "get_model",
]
