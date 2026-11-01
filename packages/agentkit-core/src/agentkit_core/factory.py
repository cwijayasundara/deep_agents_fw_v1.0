from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .registry import ModelSpec
from .settings import Settings


def get_model(spec: ModelSpec, settings: Settings) -> BaseChatModel:
    """Build a chat model; fails fast if the provider's API key is missing."""
    key = settings.require_key(spec.provider)
    model: BaseChatModel = init_chat_model(
        spec.model_id, model_provider=str(spec.provider), api_key=key, **spec.kwargs
    )
    return model
