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
from types import SimpleNamespace

from agentkit_evals import pytest_plugin
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool
def web_search(query: str) -> str:
    """search"""
    return "x"


class Model(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def fake_load(agent, model):
    call = {"name": "web_search", "args": {"query": "q"}, "id": "1", "type": "tool_call"}
    name = web_search.name if "ok" in str(agent) else "other"
    reply = AIMessage("", tool_calls=[{**call, "name": name}])
    graph = create_agent(Model(messages=iter([reply])), tools=[web_search])
    spec = SimpleNamespace(name="fake", version="1", output=None)
    return graph, spec


pytest_plugin.load_graph = fake_load
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
