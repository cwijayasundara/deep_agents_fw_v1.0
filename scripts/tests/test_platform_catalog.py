from agentkit_deep import GUARD_LAYERS
from platform_catalog import collect


def test_catalog_guards_from_constants() -> None:
    guards = collect()["middleware"]["fixed_guards"]
    assert [g["name"] for g in guards] == [g.name for g in GUARD_LAYERS]
