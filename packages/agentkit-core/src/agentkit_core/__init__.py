"""agentkit-core: settings and model registry."""

from .build_context import BuildContext
from .context import Label, PlatformContext, Scope, check_label, check_user_id, store_namespace
from .factory import get_model
from .registry import TIERS, EmbeddingSpec, ModelRegistry, ModelSpec
from .seams import ProviderMeta, Seam, provider, provider_meta
from .settings import ConfigError, Provider, Settings

__all__ = [
    "TIERS",
    "BuildContext",
    "ConfigError",
    "EmbeddingSpec",
    "Label",
    "ModelRegistry",
    "ModelSpec",
    "PlatformContext",
    "ProviderMeta",
    "Provider",
    "Scope",
    "Seam",
    "Settings",
    "check_label",
    "check_user_id",
    "get_model",
    "provider",
    "provider_meta",
    "store_namespace",
]
