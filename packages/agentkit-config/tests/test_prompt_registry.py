from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from agentkit_config import Library, SpecErrors
from agentkit_config.pools.prompts import PromptRegistry, compose
from agentkit_config.validate import _Ctx, _prompt_errors
from agentkit_core import ModelRegistry

REPO = Path(__file__).resolve().parents[3]


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _lib(tmp_path: Path) -> PromptRegistry:
    base = tmp_path / "prompts"
    for v in ("1.0.0", "1.2.0", "2.0.0", "1.10.0"):
        _w(base / "p" / f"v{v}.md", f"---\nowner: me\neval_suite: s\n---\nbody {v}\n")
    _w(base / "labels.yaml", "p: {production: 1.2.0}\n")
    _w(base / "q.md", "flat q")
    return PromptRegistry.from_roots([tmp_path])


def _ref(reg: PromptRegistry, ref: str):
    return reg.get_ref(ref, file="f", path="prompt")


def test_references_resolve_by_semver(tmp_path: Path) -> None:
    reg = _lib(tmp_path)
    assert _ref(reg, "p").version == "2.0.0"
    assert _ref(reg, "p@1").version == "1.10.0"  # numeric, not lexical
    assert _ref(reg, "p@1.2").version == "1.2.0"
    assert _ref(reg, "p@1.0.0").version == "1.0.0"
    assert _ref(reg, "p@production").version == "1.2.0"
    got = _ref(reg, "p@1.2.0")
    assert (got.owner, got.eval_suite, got.text, got.prompt_id) == (
        "me",
        "s",
        "body 1.2.0",
        "p@1.2.0",
    )
    assert "p" in reg and reg.names() == ["p", "q"]


def test_unknown_version_and_label_list_what_exists(tmp_path: Path) -> None:
    reg = _lib(tmp_path)
    with pytest.raises(SpecErrors, match=r"available: 1.0.0, 1.2.0, 1.10.0, 2.0.0"):
        _ref(reg, "p@3")
    with pytest.raises(SpecErrors, match="no label 'staging'"):
        _ref(reg, "p@staging")
    with pytest.raises(SpecErrors, match="unknown prompt 'zz'"):
        _ref(reg, "zz")


def test_flat_file_is_version_zero(tmp_path: Path) -> None:
    p = _ref(_lib(tmp_path), "q")
    assert (p.version, p.text, p.owner) == ("0.0.0", "flat q", None)


def test_flat_and_versioned_is_an_error(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/q.md", "x")
    _w(tmp_path / "prompts/q/v1.0.0.md", "y")
    with pytest.raises(SpecErrors, match="prompt 'q' is both flat and versioned"):
        PromptRegistry.from_roots([tmp_path])


def test_fragments_expand(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/frag/a.md", "A-text")
    _w(tmp_path / "prompts/main.md", "before {{> frag/a}} after {{agent_name}}")
    reg = PromptRegistry.from_roots([tmp_path])
    assert compose(_ref(reg, "main"), reg) == "before A-text after {{agent_name}}"


def test_fragment_cycle_is_a_spec_error(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/a.md", "x {{> b}}")
    _w(tmp_path / "prompts/b.md", "y {{> a}}")
    reg = PromptRegistry.from_roots([tmp_path])
    with pytest.raises(SpecErrors, match="a -> b -> a"):
        compose(_ref(reg, "a"), reg)


def test_missing_fragment_is_a_spec_error(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/a.md", "x {{> nope}}")
    reg = PromptRegistry.from_roots([tmp_path])
    with pytest.raises(SpecErrors, match="unknown prompt 'nope'"):
        compose(_ref(reg, "a"), reg)


def test_fragment_depth_limit(tmp_path: Path) -> None:
    for i in range(7):
        _w(tmp_path / f"prompts/f{i}.md", f"f{i} {{{{> f{i + 1}}}}}" if i < 6 else "leaf")
    reg = PromptRegistry.from_roots([tmp_path])
    with pytest.raises(SpecErrors, match="deeper than 5"):
        compose(_ref(reg, "f0"), reg)
    assert compose(_ref(reg, "f1"), reg).endswith("leaf")  # exactly 5 levels is fine


def test_validate_reports_bad_label_and_bad_fragment(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/p/v1.0.0.md", "x")
    _w(tmp_path / "prompts/labels.yaml", "p: {production: 9.9.9}\n")
    _w(tmp_path / "prompts/c.md", "{{> c}}")
    c = _Ctx(Library.from_roots([tmp_path]), ModelRegistry.default(), "f.yaml")
    (e,) = _prompt_errors(c, "", "p@production")
    assert "missing version 9.9.9" in e.message and "available: 1.0.0" in e.message
    assert "cycle" in _prompt_errors(c, "", "c")[0].message


def test_shipped_research_prompts_are_byte_identical_to_before_the_move() -> None:
    reg = PromptRegistry.from_roots([REPO / "libraries"])
    want = {
        "research/orchestrator": "093300afb324663dac4f9d62eec41a8f1b572d78d6b78a099fcac8d82841c8c3",
        "research/researcher": "5f0ee12159dffeb544e64edf34c3b11de13b756e8859f03168d97a04e9e66ac6",
    }
    for name, digest in want.items():
        p = _ref(reg, f"{name}@production")
        assert (p.version, p.owner) == ("1.0.0", "platform")
        assert hashlib.sha256(p.text.encode()).hexdigest() == digest
