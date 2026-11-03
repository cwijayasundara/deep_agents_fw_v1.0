"""agentkit-core: settings and model registry."""

from .build_context import BuildContext
from .context import Label, PlatformContext, Scope, check_label, check_user_id, store_namespace
from .factory import get_model
from .registry import TIERS, EmbeddingSpec, ModelRegistry, ModelSpec
from .seams import ProviderMeta, Seam, provider, provider_meta
from .secrets import SECRETS, SecretsProvider, env_secrets, resolve_secret
from .settings import ConfigError, Provider, Settings

__all__ = [
    "SECRETS",
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
    "SecretsProvider",
    "Settings",
    "check_label",
    "check_user_id",
    "env_secrets",
    "get_model",
    "provider",
    "provider_meta",
    "resolve_secret",
    "store_namespace",
]
