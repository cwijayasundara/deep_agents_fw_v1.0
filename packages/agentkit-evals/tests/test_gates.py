import json
import math
from pathlib import Path

import pytest
from agentkit_evals.gates import (
    Baseline,
    BaselineMismatch,
    GateSpec,
    MetricGate,
    check_gates,
    dataset_sha256,
    load_gates,
)


def _spec(min_cases: int = 2) -> GateSpec:
    return GateSpec(
        baseline=Path("baseline.json"),
        min_cases=min_cases,
        metrics={
            "completed": MetricGate(min=0.9),
            "groundedness": MetricGate(min=0.55, max_drop=0.10),
            "mean_total_tokens": MetricGate(max_rise=0.30),
        },
    )


def _summary(agg: dict | None = None, cases: list | None = None) -> dict:
    return {
        "aggregate": agg or {"completed": 1.0, "groundedness": 0.80, "mean_total_tokens": 1000.0},
        "cases": cases
        if cases is not None
        else [{"case_id": "a", "error": None}, {"case_id": "b", "error": None}],
        "model_id": "m",
        "judge_model_id": "j",
        "dataset": "ds.jsonl",
    }


@pytest.fixture
def ds(tmp_path):
    p = tmp_path / "ds.jsonl"
    p.write_text('{"id": "a"}\n')
    return p


@pytest.fixture
def base(ds):
    return Baseline.from_summary(
        _summary({"completed": 1.0, "groundedness": 0.82, "mean_total_tokens": 1000.0}),
        ds,
    )


def test_gate_passes_within_tolerance(base, ds):
    s = _summary({"completed": 1.0, "groundedness": 0.75, "mean_total_tokens": 1290.0})
    assert check_gates(_spec(), base, s, ds) == []


def test_gate_fails_below_floor(base, ds):
    s = _summary({"completed": 0.8, "groundedness": 0.80, "mean_total_tokens": 1000.0})
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["completed"]
    assert "0.8 < min 0.9" in fails[0].detail


def test_gate_fails_on_drop_vs_baseline(base, ds):
    s = _summary({"completed": 1.0, "groundedness": 0.70, "mean_total_tokens": 1000.0})
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["groundedness"]
    assert "0.7 dropped 0.12 from baseline 0.82 (max_drop 0.1)" in fails[0].detail


def test_gate_fails_on_token_rise(base, ds):
    s = _summary({"completed": 1.0, "groundedness": 0.82, "mean_total_tokens": 1301.0})
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["mean_total_tokens"]
    assert fails[0].detail == "1301 rose 30.1% above baseline 1000 (max_rise 30%)"


def test_gate_fails_below_min_cases(base, ds):
    s = _summary(cases=[{"case_id": "a", "error": None}])
    fails = check_gates(_spec(min_cases=2), base, s, ds)
    assert [f.metric for f in fails] == ["min_cases", "completed"]  # b: baseline case missing


def test_gate_fails_on_missing_metric(base, ds):
    s = _summary({"completed": 1.0, "mean_total_tokens": 1000.0})
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["groundedness"]
    assert "missing" in fails[0].detail


def test_gate_fails_on_newly_errored_case(base, ds):
    s = _summary(cases=[{"case_id": "a", "error": "boom"}, {"case_id": "b", "error": None}])
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["completed"]
    assert "a" in fails[0].detail and "boom" in fails[0].detail


def test_rise_and_drop_skipped_without_baseline_value(ds):
    b = Baseline.from_summary(_summary({"completed": 1.0, "mean_total_tokens": 0.0}), ds)
    s = _summary({"completed": 1.0, "groundedness": 0.6, "mean_total_tokens": 9e9})
    assert check_gates(_spec(), b, s, ds) == []


@pytest.mark.parametrize(
    "field,mutate",
    [
        ("dataset_sha256", "dataset"),
        ("model_id", "model_id"),
        ("judge_model_id", "judge_model_id"),
    ],
)
def test_gate_refuses_mismatched_baseline(base, ds, field, mutate):
    s = _summary()
    if mutate == "dataset":
        ds.write_text('{"id": "changed"}\n')
    else:
        s[mutate] = "other"
    with pytest.raises(BaselineMismatch, match=field):
        check_gates(_spec(), base, s, ds)


def test_baseline_from_summary_round_trips(base, ds, tmp_path):
    assert base.dataset_sha256 == dataset_sha256(ds)
    assert base.model_id == "m" and base.judge_model_id == "j"
    assert base.completed_cases == ["a", "b"]
    assert len(base.recorded) == 10
    again = Baseline.model_validate(json.loads(base.model_dump_json()))
    assert again == base


def test_load_gates_resolves_baseline_relative(tmp_path):
    g = tmp_path / "sub" / "gates.yaml"
    g.parent.mkdir()
    g.write_text("baseline: baseline.json\nmin_cases: 3\nmetrics:\n  completed: {min: 0.9}\n")
    spec = load_gates(g)
    assert spec.baseline == g.parent / "baseline.json"
    assert spec.metrics["completed"].min == 0.9


def test_nan_in_run_fails_the_gate(base, ds):
    s = _summary({"completed": 1.0, "groundedness": math.nan, "mean_total_tokens": 1000.0})
    fails = check_gates(_spec(), base, s, ds)
    assert [f.metric for f in fails] == ["groundedness"]
    assert "NaN" in fails[0].detail


def test_nan_in_baseline_fails_the_gate(ds):
    b = Baseline.from_summary(
        _summary({"completed": 1.0, "groundedness": math.nan, "mean_total_tokens": 1000.0}), ds
    )
    fails = check_gates(_spec(), b, _summary(), ds)
    assert [f.metric for f in fails] == ["groundedness"]
    assert "baseline" in fails[0].detail and "NaN" in fails[0].detail


@pytest.mark.parametrize(
    "gate,current,base",
    [
        (MetricGate(min=0.96), 0.9599999, None),
        (MetricGate(max=0.96), 0.9600001, None),
        (MetricGate(max_drop=0.10), 0.7199999, 0.82),
        (MetricGate(max_rise=0.30), 1300.0001, 1000.0),
    ],
)
def test_failure_detail_never_shows_equal_numbers(ds, gate, current, base):
    """A value just past a floor must not read like "0.96 < min 0.96"."""
    spec = GateSpec(baseline=Path("b.json"), min_cases=0, metrics={"m": gate})
    b = Baseline.from_summary(_summary({"m": base if base is not None else 0.0}), ds)
    if base is None:
        b.aggregate.pop("m")
    (fail,) = check_gates(spec, b, _summary({"m": current}), ds)
    import re

    nums = re.findall(r"-?\d+(?:\.\d+)?%?", fail.detail)
    if gate.min is not None or gate.max is not None:
        assert nums[0] != nums[1], fail.detail
    else:  # the moved amount vs its allowance
        assert nums[1] != nums[-1], fail.detail


@pytest.mark.parametrize(
    "gate,ok,bad,base",
    [
        (MetricGate(min=0.96), 0.96 - 1e-12, 0.96 - 1e-6, None),
        (MetricGate(max=0.96), 0.96 + 1e-12, 0.96 + 1e-6, None),
        (MetricGate(max_drop=0.10), 0.82 - 0.10, 0.82 - 0.10 - 1e-6, 0.82),
    ],
)
def test_exact_boundary_passes_within_epsilon(ds, gate, ok, bad, base):
    spec = GateSpec(baseline=Path("b.json"), min_cases=0, metrics={"m": gate})
    b = Baseline.from_summary(_summary({"m": base if base is not None else 0.0}), ds)
    if base is None:
        b.aggregate.pop("m")
    assert check_gates(spec, b, _summary({"m": ok}), ds) == []
    assert len(check_gates(spec, b, _summary({"m": bad}), ds)) == 1


def test_completed_gate_counts_24_of_25_against_a_096_floor(ds):
    spec = GateSpec(
        baseline=Path("b.json"), min_cases=0, metrics={"completed": MetricGate(min=0.96)}
    )
    b = Baseline.from_summary(_summary({"completed": 1.0}), ds)
    assert check_gates(spec, b, _summary({"completed": sum([1.0] * 24) / 25}), ds) == []


def test_baseline_case_missing_from_run_fails(base, ds):
    s = _summary(cases=[{"case_id": "a", "error": None}])
    fails = check_gates(_spec(min_cases=1), base, s, ds)
    assert [f.metric for f in fails] == ["completed"]
    assert "case b" in fails[0].detail and "missing" in fails[0].detail
