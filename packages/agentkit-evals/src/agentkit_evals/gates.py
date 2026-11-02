"""Regression gates: compare an eval summary against a committed baseline."""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

_EPS = 1e-9


class MetricGate(BaseModel):
    min: float | None = None
    max: float | None = None
    max_drop: float | None = None  # absolute, vs baseline
    max_rise: float | None = None  # relative, e.g. 0.30 = +30%


class GateSpec(BaseModel):
    baseline: Path
    min_cases: int
    metrics: dict[str, MetricGate]


def load_gates(path: Path) -> GateSpec:
    path = Path(path)
    spec = GateSpec.model_validate(yaml.safe_load(path.read_text()))
    if not spec.baseline.is_absolute():
        spec = spec.model_copy(update={"baseline": path.parent / spec.baseline})
    return spec


def dataset_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Baseline(BaseModel):
    dataset_sha256: str
    model_id: str
    judge_model_id: str
    aggregate: dict[str, float]
    completed_cases: list[str]
    recorded: str

    @classmethod
    def from_summary(cls, summary: dict[str, Any], dataset_path: Path) -> Baseline:
        return cls(
            dataset_sha256=dataset_sha256(dataset_path),
            model_id=summary["model_id"],
            judge_model_id=summary["judge_model_id"],
            aggregate=dict(summary["aggregate"]),
            completed_cases=[c["case_id"] for c in summary["cases"] if not c.get("error")],
            recorded=datetime.date.today().isoformat(),
        )


@dataclass
class GateFailure:
    metric: str
    detail: str


class BaselineMismatch(ValueError):
    """The baseline was recorded against a different dataset, model or judge."""


def _check_metric(
    name: str, gate: MetricGate, current: float, base: float | None
) -> list[GateFailure]:
    out: list[GateFailure] = []
    if gate.min is not None and current < gate.min - _EPS:
        out.append(GateFailure(name, f"{current:.2f} < min {gate.min:.2f}"))
    if gate.max is not None and current > gate.max + _EPS:
        out.append(GateFailure(name, f"{current:.2f} > max {gate.max:.2f}"))
    if gate.max_drop is not None and base is not None and current < base - gate.max_drop - _EPS:
        out.append(
            GateFailure(
                name,
                f"{current:.2f} dropped {base - current:.2f} from baseline {base:.2f} "
                f"(max_drop {gate.max_drop:.2f})",
            )
        )
    if gate.max_rise is not None and base and current > base * (1 + gate.max_rise) + _EPS:
        out.append(
            GateFailure(
                name,
                f"{current:g} rose {(current / base - 1):.0%} above baseline {base:g} "
                f"(max_rise {gate.max_rise:g})",
            )
        )
    return out


def check_gates(
    spec: GateSpec, baseline: Baseline, summary: dict[str, Any], dataset_path: Path
) -> list[GateFailure]:
    for field, recorded, now in (
        ("dataset_sha256", baseline.dataset_sha256, dataset_sha256(dataset_path)),
        ("model_id", baseline.model_id, summary.get("model_id")),
        ("judge_model_id", baseline.judge_model_id, summary.get("judge_model_id")),
    ):
        if recorded != now:
            raise BaselineMismatch(
                f"baseline {field} mismatch: baseline {recorded!r}, current {now!r}; "
                "re-record the baseline"
            )

    failures: list[GateFailure] = []
    cases = summary["cases"]
    if len(cases) < spec.min_cases:
        failures.append(
            GateFailure("min_cases", f"{len(cases)} cases < min_cases {spec.min_cases}")
        )

    aggregate = summary["aggregate"]
    for name, gate in spec.metrics.items():
        if name not in aggregate:
            failures.append(GateFailure(name, "metric missing from run"))
            continue
        failures.extend(_check_metric(name, gate, aggregate[name], baseline.aggregate.get(name)))

    errors = {c["case_id"]: c.get("error") for c in cases}
    for case_id in baseline.completed_cases:
        if errors.get(case_id):
            failures.append(
                GateFailure(
                    "completed",
                    f"case {case_id} completed in baseline, now errored: {errors[case_id]}",
                )
            )
    return failures
