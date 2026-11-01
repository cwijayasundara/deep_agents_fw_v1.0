"""Opt-in live smoke tests: `uv run pytest -m live`. Skipped per-provider when the key is unset."""

import os

import pytest
from agentkit_core import ModelRegistry, Settings, get_model

REG = ModelRegistry.default()
KEY = {
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
}


@pytest.mark.live
@pytest.mark.parametrize("entry", REG.names())
async def test_model_answers(entry):
    spec = REG.resolve(entry, "fast")
    if not os.environ.get(KEY[str(spec.provider)]):
        pytest.skip(f"{KEY[str(spec.provider)]} not set")
    reply = await get_model(spec, Settings()).ainvoke("Reply with exactly: ok")
    assert "ok" in str(reply.content).lower()
