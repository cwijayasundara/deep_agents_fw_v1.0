import pytest
from agentkit_config.pools.code import CodePools, check_params


def test_entry_points_registered():
    pools = CodePools.from_entry_points()
    assert {"web_search", "fetch_url"} <= set(pools.tools.names())
    assert "call_limit" in pools.middleware.names()


def test_override_replaces_only_named():
    def fake(ctx):
        return None

    pools = CodePools.from_entry_points().override(tools={"web_search": fake})
    assert pools.tools.get("web_search", file="f", path="p") is fake
    assert "fetch_url" in pools.tools
    assert "call_limit" in pools.middleware


def test_check_params_rejects_unknown_kwarg():
    def factory(ctx, *, a: int = 1): ...

    assert check_params(factory, {"a": 2}) is None
    assert "unexpected keyword argument 'bogus'" in (check_params(factory, {"bogus": 1}) or "")


def test_override_rejects_unknown_pool():
    with pytest.raises(TypeError, match="unknown pool"):
        CodePools.from_entry_points().override(bogus={"x": 1})
