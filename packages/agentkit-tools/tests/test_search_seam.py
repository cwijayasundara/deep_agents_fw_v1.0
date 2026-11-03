import sys
from importlib.metadata import EntryPoint, entry_points

import pytest
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_core import seams as seams_mod
from agentkit_core.seams import provider
from agentkit_tools import Source
from agentkit_tools.factories import _names, web_search


def _ctx(**env: str) -> BuildContext:
    settings = Settings(_env_file=None, **env)  # type: ignore[arg-type]
    return BuildContext(settings, ModelRegistry.default().resolve(), "agent")


class _FakeSearch:
    async def search(self, query: str, k: int = 5) -> list[Source]:
        return [Source("https://fake.test", "fake", f"hit for {query}")]


@provider(owner="tenant-x", version="1.0.0")
def fake(settings):
    return _FakeSearch()


def _with_fake(monkeypatch):
    # Pytest imports test modules by path (importlib mode), so expose this one by name.
    monkeypatch.setitem(sys.modules, "test_search_seam_fake", sys.modules[__name__])
    ep = EntryPoint("fake", "test_search_seam_fake:fake", "agentkit.search_backends")
    real = list(entry_points(group="agentkit.search_backends"))
    monkeypatch.setattr(seams_mod, "entry_points", lambda group: [*real, ep])


async def test_third_party_backend_is_used_without_editing_agentkit_tools(monkeypatch):
    _with_fake(monkeypatch)
    tool = web_search(_ctx(), backend="fake")
    out = await tool.ainvoke({"query": "rag"})
    assert "https://fake.test" in out and "hit for rag" in out


def test_auto_order_unchanged_with_only_builtins(monkeypatch):
    _with_fake(monkeypatch)
    ctx = _ctx(parallel_api_key="p", brave_api_key="b", tavily_api_key="t")
    assert _names(ctx, "auto") == ["parallel", "brave", "tavily", "duckduckgo"]


def test_unknown_backend_lists_known():
    with pytest.raises(ConfigError, match="unknown web_search backend provider 'nope'"):
        web_search(_ctx(), backend="nope")
