from agentkit_deep import GUARD_LAYERS
from platform_catalog import collect


def test_catalog_guards_from_constants() -> None:
    guards = collect()["middleware"]["fixed_guards"]
    assert [g["name"] for g in guards] == [g.name for g in GUARD_LAYERS]


def test_catalog_memory_tiers_from_constants() -> None:
    from agentkit_deep import MEMORY_ROUTES

    paths = [t["path"] for t in collect()["memory_tiers"]]
    assert paths == [*(r.path for r in MEMORY_ROUTES), "everything else (/report.md, scratch)"]
