"""agentkit-core: settings and model registry."""

from .build_context import BuildContext
from .context import Label, PlatformContext, Scope, check_label, check_user_id, store_namespace
from .factory import get_model
from .registry import TIERS, ModelRegistry, ModelSpec
from .settings import ConfigError, Provider, Settings

__all__ = [
    "TIERS",
    "BuildContext",
    "ConfigError",
    "Label",
    "ModelRegistry",
    "ModelSpec",
    "PlatformContext",
    "Provider",
    "Scope",
    "Settings",
    "check_label",
    "check_user_id",
    "get_model",
    "store_namespace",
]
