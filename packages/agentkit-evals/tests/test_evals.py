import pytest
from agentkit_evals import (
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
