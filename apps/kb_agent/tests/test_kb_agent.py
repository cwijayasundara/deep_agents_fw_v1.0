"""Offline tests for the pilot kb_agent: builds, curated tools, golden set, gates."""

from pathlib import Path

import pytest
from agentkit_config import CodePools, Library, load_agent
from agentkit_config.cli import main as agentkit_main
from agentkit_config.resolve import resolve_agent
from agentkit_config.spec import parse_agent
from agentkit_core import ModelRegistry, Settings
from agentkit_deep.testing import scripted
from agentkit_evals import load_dataset, load_gates
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "apps" / "kb_agent" / "agent.yaml"
RESEARCH = ROOT / "apps" / "research_agent" / "agent.yaml"
EVALS = ROOT / "apps" / "kb_agent" / "evals"
SETTINGS = Settings(_env_file=None, fireworks_api_key="f", openai_api_key="o")  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("AGENTKIT_LIBRARY_PATH", raising=False)
    # Both are kb_reader DSNs at run time; building connects to nothing (engines are lazy).
    monkeypatch.setenv("KB_DATABASE_URL", "postgresql://kb_reader:pw@127.0.0.1:1/db")
    monkeypatch.setenv("KB_READER_DATABASE_URL", "postgresql://kb_reader:pw@127.0.0.1:1/db")


def _resolve(path: Path) -> dict:
    lib = Library.for_file(path, CodePools.from_entry_points())
    return resolve_agent(
        parse_agent(path),
        lib,
        ModelRegistry.default(),
        SETTINGS,
        model=scripted(AIMessage(content="x")),
    )


def test_builds_with_the_curated_tools():
    path = AGENT
    loaded = load_agent(
        path,
        settings=SETTINGS,
        library=Library.for_file(path, CodePools.from_entry_points()),
        model=scripted(AIMessage(content="x")),
    )
    assert loaded.spec.name == "kb_agent"
    assert loaded.spec.output == "/report.md"
    assert loaded.graph is not None
    assert {t.name for t in _resolve(path)["tools"]} == {"kb_search", "sql_query"}


def test_middleware_stack_matches_the_research_agent():
    kb, research = _resolve(AGENT)["middleware"], _resolve(RESEARCH)["middleware"]
    kb_names = [type(m).__name__ for m in kb]
    # Research also has SelectionMiddleware first; the kb agent runs with selection off.
    assert kb_names == [
        type(m).__name__ for m in research if type(m).__name__ != "SelectionMiddleware"
    ]
    assert kb_names == [
        "ModelFallbackMiddleware",
        "ModelRetryMiddleware",
        "RequireOutputMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "PIIMiddleware",
        "PIIMiddleware",
    ]


def test_limits():
    spec = parse_agent(AGENT)
    limits = {
        m.params["tool_name"]: m.params["run_limit"]
        for m in spec.middleware
        if m.type == "tool_call_limit"
    }
    assert limits == {"kb_search": 15, "sql_query": 5}
    (calls,) = [m for m in spec.middleware if m.type == "call_limit"]
    assert calls.params["max_model_calls"] == 30


def test_agentkit_validate_reports_no_errors(capsys):
    assert agentkit_main(["validate", str(AGENT)]) == 0
    assert "0 error(s)" in capsys.readouterr().out


def test_golden_set():
    cases = load_dataset(EVALS / "golden.jsonl")
    assert len(cases) == 20
    for c in cases:
        assert c.expect_tools == ["kb_search"]
        assert 2 <= len(c.must_cover) <= 3
        assert c.tags[0] in {"definition", "how-to", "config", "history"}


def test_gates_use_their_own_baseline_path():
    spec = load_gates(EVALS / "gates.yaml")
    assert spec.baseline == EVALS / "baseline.json"
    assert spec.min_cases == 20
    assert spec.metrics["citation_validity"].min == 0.85
    assert spec.metrics["tool_recall"].min == 0.95
