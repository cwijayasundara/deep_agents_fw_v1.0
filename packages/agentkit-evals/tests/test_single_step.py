from __future__ import annotations

from typing import Any

import pytest
from agentkit_evals import (
    CaseResult,
    EvalCase,
    ExpectCall,
    RunResult,
    StepResult,
    run_eval,
    single_step,
    step_pass,
    tool_call_ratio,
)
from agentkit_evals.runner import aggregate
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import Field


class Recorder(GenericFakeChatModel):
    seen: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> Recorder:
        return self

    def _generate(self, messages, *a, **kw):
        self.seen.append(list(messages))
        return super()._generate(messages, *a, **kw)


def call(name: str, args: dict, id: str = "1") -> AIMessage:
    return AIMessage(content="thinking", tool_calls=[{"name": name, "args": args, "id": id}])


def build(*replies: AIMessage):
    ran: list[str] = []

    @tool
    def web_search(query: str) -> str:
        """search"""
        ran.append(query)
        return "result"

    model = Recorder(messages=iter(replies))
    return create_agent(model, tools=[web_search]), model, ran


def step_case(name="^web_search$", args=None, **kw) -> EvalCase:
    return EvalCase(
        id="s",
        question="q",
        kind="single_step",
        expect_call=ExpectCall(name=name, args=args or {}),
        **kw,
    )


async def test_stops_at_first_tool_call_without_running_the_tool():
    graph, model, ran = build(call("web_search", {"query": "mcp"}), AIMessage(content="done"))
    step = await single_step(graph, step_case(), config={}, context=None)
    assert (step.name, step.args, step.text) == ("web_search", {"query": "mcp"}, "thinking")
    assert ran == [] and len(model.seen) == 1


async def test_name_and_arg_regex_match_scores_one():
    graph, _, _ = build(call("web_search", {"query": "Model Context Protocol"}))
    case = step_case(args={"query": "Context Protocol"})
    step = await single_step(graph, case, config={}, context=None)
    assert step_pass(case, step) == 1.0


def test_wrong_name_and_wrong_arg_score_zero_with_reasons():
    from agentkit_evals import step_failure

    case = step_case(args={"query": "mcp"})
    wrong = StepResult("fetch_url", {"url": "u"})
    assert step_pass(case, wrong) == 0.0
    assert step_failure(case, wrong) == "called fetch_url, expected ^web_search$"
    assert "does not match" in (step_failure(case, StepResult("web_search", {"query": "x"})) or "")
    assert "missing arg" in (step_failure(case, StepResult("web_search", {})) or "")


async def test_text_only_reply_is_a_zero_not_an_exception():
    graph, _, _ = build(AIMessage(content="I know this already."))
    step = await single_step(graph, step_case(), config={}, context=None)
    assert step == StepResult(None, {}, "I know this already.")

    async def run_step(case):
        return step

    (r,) = await run_eval([step_case()], _no_full, _no_judge, run_step=run_step)
    assert r.scores == {"step_pass": 0.0} and r.reason == "no tool call" and r.error is None


async def test_first_delegation_is_the_scored_call():
    graph, _, ran = build(call("task", {"description": "d"}))
    step = await single_step(graph, step_case(name="^task$"), config={}, context=None)
    assert step.name == "task" and ran == []


async def test_message_prefix_reaches_the_model():
    graph, model, _ = build(call("web_search", {"query": "x"}, "n"))
    case = step_case(
        messages=[
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"name": "web_search", "args": {"query": "a"}, "id": "t1"}],
            },
            {"role": "tool", "tool_call_id": "t1", "name": "web_search", "content": "R"},
        ]
    )
    await single_step(graph, case, config={}, context=None)
    got = model.seen[0]
    assert [type(m) for m in got] == [HumanMessage, AIMessage, ToolMessage]
    assert got[1].tool_calls[0]["name"] == "web_search" and got[2].tool_call_id == "t1"


async def test_without_prefix_the_question_is_the_user_turn():
    graph, model, _ = build(call("web_search", {"query": "x"}))
    await single_step(graph, step_case(), config={}, context=None)
    assert [(type(m), m.content) for m in model.seen[0]] == [(HumanMessage, "q")]


async def test_subagent_namespace_calls_are_ignored():
    class Fake:
        async def astream(self, *a, **kw):
            yield ("task:1",), {"model": {"messages": [call("fetch_url", {"url": "u"})]}}
            yield (), {"model": {"messages": [call("web_search", {"query": "q"})]}}

    step = await single_step(Fake(), step_case(), config={}, context=None)
    assert step.name == "web_search"


def test_tool_call_ratio():
    case = EvalCase(id="c", question="q", must_cover=["x"], ideal_tool_calls=4)
    assert tool_call_ratio(case, ["a"] * 6) == 1.5
    assert tool_call_ratio(EvalCase(id="c", question="q", must_cover=["x"]), ["a"]) is None


def test_case_validation():
    with pytest.raises(ValueError, match="expect_call"):
        EvalCase(id="c", question="q", kind="single_step")
    with pytest.raises(ValueError, match="must_cover"):
        EvalCase(id="c", question="q")


async def _no_judge(case, report, retrieved):
    return {"groundedness": 1.0}


async def _no_full(q):
    raise AssertionError("single-step cases must not run the full agent")


async def test_mixed_dataset_scores_each_kind_its_own_way():
    full = EvalCase(id="f", question="fq", must_cover=["x"], ideal_tool_calls=2)
    judged: list[str] = []

    async def judge(case, report, retrieved):
        judged.append(case.id)
        return {"groundedness": 1.0}

    async def agent(q):
        return RunResult(
            "## Sources\nhttps://a.com", "https://a.com", tool_calls=["web_search"] * 3
        )

    async def run_step(case):
        return StepResult("web_search", {"query": "x"}, "t")

    by = {
        r.case_id: r for r in await run_eval([full, step_case()], agent, judge, run_step=run_step)
    }
    assert judged == ["f"]
    assert by["s"].scores == {"step_pass": 1.0} and by["s"].report == "t" and by["s"].reason is None
    assert by["f"].scores["tool_call_ratio"] == 1.5 and "step_pass" not in by["f"].scores
    assert by["f"].report.startswith("## Sources")
    agg = aggregate(list(by.values()))
    assert agg["completed"] == 1.0 and agg["step_pass"] == 1.0


async def test_single_step_case_without_step_runner_is_an_error_result():
    (r,) = await run_eval([step_case()], _no_full, _no_judge)
    assert r.error and "step runner" in r.error


async def test_full_run_scores_unchanged_regression():
    case = EvalCase(
        id="c",
        question="q",
        must_cover=["x"],
        expect_tools=["web_search", "fetch_url"],
        min_sources=2,
    )

    async def agent(q):
        return RunResult(
            "## Sources\nhttps://a.com https://b.com", "https://a.com", tool_calls=["web_search"]
        )

    async def judge(case, report, retrieved):
        return {"groundedness": 1.0, "completeness": 0.5}

    (r,) = await run_eval([case], agent, judge)
    assert r.scores == {
        "has_citation": 1.0,
        "citation_validity": 0.5,
        "sources_section": 1.0,
        "source_count_ok": 1.0,
        "tool_recall": 0.5,
        "groundedness": 1.0,
        "completeness": 0.5,
    }
    assert isinstance(r, CaseResult) and r.reason is None


def test_shipped_steps_dataset_and_gates_load():
    from pathlib import Path

    from agentkit_evals import load_dataset, load_gates

    root = Path(__file__).parents[3] / "apps/research_agent/evals"
    cases = load_dataset(root / "steps.jsonl")
    assert len(cases) == 12 and all(c.kind == "single_step" for c in cases)
    spec = load_gates(root / "gates_steps.yaml")
    assert spec.baseline.name == "baseline_steps.json"
    assert spec.metrics["step_pass"].min == 0.80 and spec.metrics["completed"].min == 1.0
