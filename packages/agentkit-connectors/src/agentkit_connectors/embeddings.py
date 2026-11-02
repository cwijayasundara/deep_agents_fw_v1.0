from __future__ import annotations

from agentkit_core import ModelRegistry, Provider, Settings
from langchain_core.embeddings import Embeddings


def embedding_dimensions(entry: str) -> int:
    return ModelRegistry.default().embedding(entry).dimensions


def get_embeddings(entry: str, settings: Settings) -> Embeddings:
    spec = ModelRegistry.default().embedding(entry)
    key = settings.require_key(spec.provider)
    if spec.provider is Provider.FIREWORKS:
        from langchain_fireworks import FireworksEmbeddings

        return FireworksEmbeddings(model=spec.model_id, api_key=key)  # type: ignore[arg-type]
    if spec.provider is Provider.OPENAI:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=spec.model_id, api_key=key)  # type: ignore[arg-type]
    from agentkit_core import ConfigError

    raise ConfigError(f"no embeddings support for provider '{spec.provider}'")
