from pathlib import Path

import pytest
from agentkit_evals import (
    CaseResult,
    EvalCase,
    RunResult,
    aggregate,
    citation_scores,
    load_dataset,
    run_eval,
    to_markdown,
)


def test_citation_scores():
    s = citation_scores(
        "x [1] https://a.com, https://fake.com.", "got https://a.com/ https://a.com"
    )
    assert s["has_citation"] == 1.0 and s["citation_validity"] == 0.5
    assert citation_scores("no links", "https://a.com") == {
        "has_citation": 0.0,
        "citation_validity": 0.0,
    }


def test_dataset_validation(tmp_path):
    p = tmp_path / "d.jsonl"
    p.write_text(
        '{"id":"a","question":"q","must_cover":["x"]}\n{"id":"a","question":"q","must_cover":["x"]}\n'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(p)
    p.write_text('{"id":"a","question":"q","must_cover":[]}\n')
    with pytest.raises(ValueError):
        load_dataset(p)


async def stub_judge(case, report, retrieved):
    return {"groundedness": 1.0, "completeness": 0.5}


async def test_run_eval_scores_and_isolates_errors():
    cases = [EvalCase(id=i, question="q", must_cover=["x"]) for i in ("ok", "boom", "empty")]

    calls = iter(
        [
            RunResult("cited https://a.com", "https://a.com"),
            RuntimeError("provider down"),
            RunResult("   ", ""),
        ]
    )

    async def agent(q):
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    results = await run_eval(cases, agent, stub_judge, concurrency=1)
    by = {r.case_id: r for r in results}
    assert by["ok"].scores == {
        "has_citation": 1.0,
        "citation_validity": 1.0,
        "groundedness": 1.0,
        "completeness": 0.5,
        "sources_section": 0.0,
        "source_count_ok": 1.0,
        "tool_recall": 0.0,
    }
    assert "provider down" in (by["boom"].error or "")
    assert by["empty"].error == "empty report"
    agg = aggregate(results)
    assert agg["completed"] == pytest.approx(1 / 3) and agg["completeness"] == 0.5
    assert "| ok |" in to_markdown(results)


async def test_case_results_carry_run_id_trace_id_and_usage():
    cases = [EvalCase(id=i, question="q", must_cover=["x"]) for i in ("ok", "empty", "judge")]
    usage = {"input_tokens": 20, "output_tokens": 6}
    runs = {
        "ok": RunResult("cited https://a.com", "https://a.com", "r1", "t1", usage),
        "empty": RunResult("  ", "", "r2", None, usage),
        "judge": RunResult("cited https://a.com", "https://a.com", "r3", "t3", None),
    }
    order = iter(["ok", "empty", "judge"])

    async def agent(q):
        return runs[next(order)]

    async def judge(case, report, retrieved):
        if case.id == "judge":
            raise RuntimeError("judge down")
        return {}

    by = {r.case_id: r for r in await run_eval(cases, agent, judge, concurrency=1)}
    assert (by["ok"].run_id, by["ok"].trace_id, by["ok"].usage) == ("r1", "t1", usage)
    assert (by["empty"].run_id, by["empty"].error) == ("r2", "empty report")
    assert (by["judge"].run_id, by["judge"].trace_id) == ("r3", "t3")
    assert "judge down" in (by["judge"].error or "")


SMOKE = Path(__file__).parents[3] / "apps/research_agent/evals/smoke.jsonl"


def test_case_defaults_keep_smoke_valid():
    cases = load_dataset(SMOKE)
    assert cases and all(
        c.tags == [] and c.expect_tools == ["web_search"] and c.min_sources == 1 for c in cases
    )


def test_sources_section():
    from agentkit_evals.metrics import sources_section

    assert sources_section("body\n## Sources\n- x") == 1.0
    assert sources_section("# sources") == 1.0
    assert sources_section("###Sources:\n") == 1.0
    assert sources_section("see the sources below") == 0.0
    assert sources_section("## Resources") == 0.0


def test_source_count_ok():
    from agentkit_evals.metrics import source_count_ok

    r = "https://a.com and https://b.com"
    assert source_count_ok(r, 2) == 1.0
    assert source_count_ok(r, 3) == 0.0
    assert source_count_ok("none", 1) == 0.0


def test_tool_recall():
    from agentkit_evals.metrics import tool_recall

    assert tool_recall(["web_search", "fetch_url"], ["task", "web_search"]) == 0.5
    assert tool_recall([], []) == 1.0
    assert tool_recall(["web_search"], ["web_search", "web_search"]) == 1.0


async def test_run_eval_adds_trajectory_scores():
    case = EvalCase(
        id="c",
        question="q",
        must_cover=["x"],
        expect_tools=["web_search", "fetch_url"],
        min_sources=2,
    )

    async def agent(q):
        return RunResult(
            "## Sources\nhttps://a.com https://b.com", "", tool_calls=["web_search"], latency_s=1.5
        )

    (r,) = await run_eval([case], agent, stub_judge)
    assert r.error is None
    assert r.scores["sources_section"] == 1.0
    assert r.scores["source_count_ok"] == 1.0
    assert r.scores["tool_recall"] == 0.5
    assert r.tool_calls == ["web_search"] and r.latency_s == 1.5


def test_aggregate_latency_and_tokens():
    ok1 = CaseResult("a", {"s": 1.0}, latency_s=2.0, usage={"input_tokens": 10, "output_tokens": 5})
    ok2 = CaseResult("b", {"s": 1.0}, latency_s=4.0, usage={"input_tokens": 20, "output_tokens": 5})
    bad = CaseResult(
        "c", error="boom", latency_s=100.0, usage={"input_tokens": 999, "output_tokens": 1}
    )
    agg = aggregate([ok1, ok2, bad])
    assert agg["mean_latency_s"] == 3.0 and agg["mean_total_tokens"] == 20.0
    bare = aggregate([CaseResult("d", {"s": 1.0})])
    assert "mean_latency_s" not in bare and "mean_total_tokens" not in bare
    assert "| a |" in to_markdown([ok1, ok2, bad])


def _cases():
    from agentkit_evals import EvalCase

    return [
        EvalCase(id="a", question="qa", must_cover=["x"], tags=["definition"]),
        EvalCase(id="b", question="qb", must_cover=["x"], tags=["comparison"]),
        EvalCase(id="c", question="qc", must_cover=["x"], tags=["comparison", "recent"]),
    ]


def test_select_cases_without_filters_keeps_all():
    from agentkit_evals import select_cases

    assert [c.id for c in select_cases(_cases())] == ["a", "b", "c"]


def test_select_cases_unions_ids_and_tags_in_dataset_order():
    from agentkit_evals import select_cases

    picked = select_cases(_cases(), ids=["c", "a"], tags=["recent"])
    assert [c.id for c in picked] == ["a", "c"]
    assert [c.id for c in select_cases(_cases(), tags=["comparison"])] == ["b", "c"]


def test_select_cases_unknown_id_names_it():
    from agentkit_evals import select_cases

    with pytest.raises(ValueError, match="nope"):
        select_cases(_cases(), ids=["a", "nope"])


def test_select_cases_no_match_is_an_error():
    from agentkit_evals import select_cases

    with pytest.raises(ValueError, match="no cases match"):
        select_cases(_cases(), tags=["missing"])
