from typing import Any

import pytest
from agentkit_deep import GUARD_LAYERS, MEMORY_ROUTES, build_deep_agent, factory
from agentkit_deep.memory import memory_backend
from agentkit_deep.testing import scripted
from deepagents.backends import StateBackend


def test_factory_follows_guard_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    real = factory.create_deep_agent

    def spy(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(factory, "create_deep_agent", spy)
    sub = {"name": "r", "description": "d", "system_prompt": "s"}
    build_deep_agent(model=scripted(), system_prompt="p", subagents=[sub])
    names = [g.name for g in GUARD_LAYERS]
    assert [type(m).__name__ for m in seen["middleware"][: len(names)]] == names
    assert seen["subagents"]
    for spec in seen["subagents"]:
        assert type(spec["middleware"][0]).__name__ == GUARD_LAYERS[-1].name


def test_memory_routes_match_backend() -> None:
    backend = memory_backend({"/skills/<owner>/": StateBackend()})
    assert {r.path for r in MEMORY_ROUTES} == set(backend.routes)
