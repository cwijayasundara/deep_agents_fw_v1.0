from __future__ import annotations

import json

import pytest

pytest_plugins = ["pytester"]

CASES = [
    {
        "id": "case-a",
        "question": "q a",
        "kind": "single_step",
        "expect_call": {"name": "^web_search$"},
    },
    {
        "id": "case-b",
        "question": "q b",
        "kind": "single_step",
        "expect_call": {"name": "^web_search$"},
    },
]

CONFTEST = '''
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentkit_evals import pytest_plugin
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """search"""
    return "x"


class Model(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class FakeJudge:
    async def __call__(self, case, report, retrieved):
        return {"saw_subagent": 1.0 if "SUBAGENT-OUT" in retrieved else 0.0}


class FullGraph:
    """Streams a subagent tool result that never reaches the top-level messages."""

    async def astream(self, inputs, config=None, context=None, stream_mode=None, subgraphs=False):
        assert subgraphs and "values" in stream_mode
        tc = {"name": "web_search", "args": {}, "id": "s", "type": "tool_call"}
        sub = AIMessage("", tool_calls=[tc])
        yield ("task:1",), "updates", {"model": {"messages": [sub]}}
        out = ToolMessage("SUBAGENT-OUT http://x.test", tool_call_id="s", name="web_search")
        yield ("task:1",), "updates", {"tools": {"messages": [out]}}
        yield (), "values", {"messages": [AIMessage("report body")]}


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    monkeypatch.setattr(pytest_plugin, "load_graph", fake_load)
    monkeypatch.setattr(pytest_plugin, "load_judge", lambda: FakeJudge())


def fake_load(agent, model):
    spec = SimpleNamespace(name="fake", version="1", output=None)
    if Path(agent).stem == "full":
        return FullGraph(), spec
    call = {"name": "web_search", "args": {"query": "q"}, "id": "1", "type": "tool_call"}
    name = web_search.name if Path(agent).stem == "ok" else "other"
    reply = AIMessage("", tool_calls=[{**call, "name": name}])
    graph = create_agent(Model(messages=iter([reply])), tools=[web_search])
    return graph, spec
'''

TEST = """
import pytest
from agentkit_evals.pytest_plugin import assert_case


@pytest.mark.agentkit_eval(dataset="cases.jsonl", agent="%s.yaml", kind="single_step")
def test_steps(case, agentkit_run):
    assert_case(agentkit_run(case), step_pass=1.0)


def test_plain():
    assert True
"""


def make(pytester: pytest.Pytester, agent: str) -> None:
    pytester.makefile(".jsonl", cases="\n".join(json.dumps(c) for c in CASES))
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_eval=TEST % agent)


def test_skipped_without_live_flag(pytester: pytest.Pytester) -> None:
    make(pytester, "ok")
    res = pytester.runpytest_inprocess("-rs")
    res.assert_outcomes(passed=1, skipped=2)
    res.stdout.fnmatch_lines(["*live eval; pass --agentkit-live*"])


def test_live_one_test_per_case(pytester: pytest.Pytester) -> None:
    make(pytester, "ok")
    res = pytester.runpytest_inprocess("-v", "--agentkit-live")
    res.assert_outcomes(passed=3)
    res.stdout.fnmatch_lines(["*test_steps[[]case-a[]] PASSED*", "*test_steps[[]case-b[]] PASSED*"])


def test_failure_message_has_case_id_and_reason(pytester: pytest.Pytester) -> None:
    make(pytester, "bad")
    res = pytester.runpytest_inprocess("--agentkit-live")
    res.assert_outcomes(passed=1, failed=2)
    res.stdout.fnmatch_lines(["*case case-a*step_pass=0.00*reason:*"])


def test_marker_registered_and_options(pytester: pytest.Pytester) -> None:
    res = pytester.runpytest_inprocess("--markers")
    res.stdout.fnmatch_lines(["*agentkit_eval(dataset, agent, kind)*"])
    res = pytester.runpytest_inprocess("--help")
    res.stdout.fnmatch_lines(["*--agentkit-live*", "*--agentkit-model=ENTRY*"])


FULL_TEST = """
import pytest
from agentkit_evals.pytest_plugin import assert_case


@pytest.mark.agentkit_eval(dataset="full.jsonl", agent="full.yaml")
def test_full(case, agentkit_run):
    result = agentkit_run(case)
    assert result.latency_s is not None
    assert "web_search" in result.tool_calls
    assert_case(result, saw_subagent=1.0)
"""


def test_full_run_collects_subagent_output_and_uses_dataset_kind(
    pytester: pytest.Pytester,
) -> None:
    case = {"id": "f1", "question": "q", "must_cover": ["x"]}
    pytester.makefile(".jsonl", full=json.dumps(case))
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_full=FULL_TEST)
    res = pytester.runpytest_inprocess("--agentkit-live")
    res.assert_outcomes(passed=1)
