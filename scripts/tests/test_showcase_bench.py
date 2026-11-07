from __future__ import annotations

import platform_catalog
import pytest
import yaml
from agentkit_config.cli import main as validate_main
from showcase.bench import build_bench
from showcase.redact import ROOT, example_tenant_policy


@pytest.fixture(scope="module")
def catalog():
    return platform_catalog.collect()


@pytest.fixture(scope="module")
def bench(catalog):
    return build_bench(catalog)


def test_templates_are_shipped_agents(bench, catalog):
    assert len(bench["templates"]) == 2
    assert {t["base"] for t in bench["templates"]} == {a["name"] for a in catalog["apps"]}
    by = {t["base"]: t for t in bench["templates"]}
    assert by["kb_agent"]["commands"] == "kb"
    assert by["research_agent"]["commands"] == "research"


def test_options_cover_registered_tools(bench, catalog):
    assert {t["name"] for t in bench["options"]["tools"]} == {t["name"] for t in catalog["tools"]}
    kb = next(t for t in bench["options"]["tools"] if t["name"] == "kb_search")
    assert kb["side_effect"] == "read"
    assert any(p["name"] == "query" and p["required"] for p in kb["params"])


def test_policy_is_example_tenant(bench):
    assert bench["policy"]["example_tenant"] == example_tenant_policy()
    assert bench["policy"]["classes"] == ["read", "write", "external"]


def test_rule_ids(bench):
    assert [r["id"] for r in bench["rules"]] == [
        "side_effect_not_allowed",
        "missing_require_output",
        "unknown_part",
        "kb_tool_without_connector",
        "subagent_unknown_tool",
    ]
    assert all(
        r["message"].endswith("— `agentkit validate` is the authority") for r in bench["rules"]
    )


def test_kb_commands_list_prereqs(bench):
    kb = "\n".join(bench["commands"]["kb"])
    assert "agentkit-kb setup" in kb
    assert "KB_READER_DATABASE_URL" in kb
    assert bench["commands"]["research"] == [
        "uv run agentkit validate {file}",
        "uv run research --agent {file}",
    ]


def test_template_spec_passes_real_validate(bench, tmp_path, monkeypatch):
    # tmp_path has no `libraries/` ancestor; point the library search path at the repo's.
    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", str(ROOT / "libraries"))
    for t in bench["templates"]:
        path = tmp_path / f"{t['name']}.yaml"
        path.write_text(yaml.safe_dump(t["spec"], sort_keys=False))
        assert validate_main(["validate", str(path)]) == 0, t["name"]
