from __future__ import annotations

import pytest
from agentkit_config.errors import SpecErrors
from agentkit_config.registry import Registry


def test_duplicate_names_both_sources() -> None:
    reg: Registry[int] = Registry("thing")
    reg.register("a", 1, source="one.md")
    with pytest.raises(SpecErrors) as ei:
        reg.register("a", 2, source="two.md")
    assert "one.md" in str(ei.value) and "two.md" in str(ei.value)


def test_unknown_lists_known() -> None:
    reg: Registry[int] = Registry("thing", {"b": 1, "a": 2})
    with pytest.raises(SpecErrors) as ei:
        reg.get("zz", file="f.yaml", path="x")
    assert "a, b" in str(ei.value) and ei.value.errors[0].path == "x"


def test_replaced_returns_new_instance() -> None:
    reg: Registry[int] = Registry("thing", {"a": 1})
    new = reg.replaced({"a": 5, "b": 6})
    assert new is not reg and "b" in new and "b" not in reg
    assert new.get("a", file="f", path="p") == 5 and reg.get("a", file="f", path="p") == 1
    assert new.names() == ["a", "b"]
