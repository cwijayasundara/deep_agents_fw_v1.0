from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from .dataset import EvalCase
from .judge import Judge
from .metrics import (
    citation_scores,
    source_count_ok,
    sources_section,
    step_failure,
    tool_call_ratio,
    tool_recall,
)
from .single_step import StepResult


@dataclass
class RunResult:
    report: str
    retrieved: str  # concatenated tool output the agent actually saw
    run_id: str | None = None  # the agent run's root run id (the cost ledger's key)
    trace_id: str | None = None  # its trace id when tracing is on
    usage: dict[str, Any] | None = None  # the run's ledger row (token counts), if recorded
    tool_calls: list[str] = field(default_factory=list)  # tool names in call order, all agents
    latency_s: float | None = None


@dataclass
class CaseResult:
    case_id: str
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    run_id: str | None = None
    trace_id: str | None = None
    usage: dict[str, Any] | None = None
    latency_s: float | None = None
    tool_calls: list[str] = field(default_factory=list)
    reason: str | None = None  # why a single-step case failed
    report: str = ""  # the full report (full runs) or the step's text (single-step)


AgentRunner = Callable[[str], Awaitable[RunResult]]
StepRunner = Callable[[EvalCase], Awaitable[StepResult]]


async def _one_step(case: EvalCase, run_step: StepRunner | None) -> CaseResult:
    if run_step is None:
        return CaseResult(case.id, error="single_step case but no step runner")
    started = time.monotonic()
    try:
        step = await run_step(case)
    except Exception as e:
        return CaseResult(case.id, error=f"{type(e).__name__}: {e}")
    reason = step_failure(case, step)
    return CaseResult(
        case.id,
        scores={"step_pass": 0.0 if reason else 1.0},
        latency_s=time.monotonic() - started,
        tool_calls=[step.name] if step.name else [],
        reason=reason,
        report=step.text,
    )


async def _one(
    case: EvalCase, run_agent: AgentRunner, judge: Judge, run_step: StepRunner | None = None
) -> CaseResult:
    if case.kind == "single_step":
        return await _one_step(case, run_step)
    try:
        r = await run_agent(case.question)
    except Exception as e:  # one bad case must not sink the run
        return CaseResult(case.id, error=f"{type(e).__name__}: {e}")
    result = CaseResult(
        case.id,
        run_id=r.run_id,
        trace_id=r.trace_id,
        usage=r.usage,
        latency_s=r.latency_s,
        tool_calls=list(r.tool_calls),
        report=r.report,
    )
    try:
        if not r.report.strip():
            result.error = "empty report"
            return result
        result.scores = citation_scores(r.report, r.retrieved)
        result.scores["sources_section"] = sources_section(r.report)
        result.scores["source_count_ok"] = source_count_ok(r.report, case.min_sources)
        result.scores["tool_recall"] = tool_recall(case.expect_tools, r.tool_calls)
        ratio = tool_call_ratio(case, r.tool_calls)
        if ratio is not None:
            result.scores["tool_call_ratio"] = ratio
        result.scores.update(await judge(case, r.report, r.retrieved))
    except Exception as e:
        result.scores, result.error = {}, f"{type(e).__name__}: {e}"
    return result


async def run_eval(
    cases: list[EvalCase],
    run_agent: AgentRunner,
    judge: Judge,
    concurrency: int = 2,
    run_step: StepRunner | None = None,
) -> list[CaseResult]:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(c: EvalCase) -> CaseResult:
        async with sem:
            return await _one(c, run_agent, judge, run_step)

    return list(await asyncio.gather(*(guarded(c) for c in cases)))


def aggregate(results: list[CaseResult]) -> dict[str, float]:
    ok = [r for r in results if r.error is None]
    keys = sorted({k for r in ok for k in r.scores})
    agg = {k: mean(r.scores[k] for r in ok if k in r.scores) for k in keys}
    latencies = [r.latency_s for r in ok if r.latency_s is not None]
    if latencies:
        agg["mean_latency_s"] = mean(latencies)
    tokens = [
        r.usage["input_tokens"] + r.usage["output_tokens"]
        for r in ok
        if r.usage and "input_tokens" in r.usage and "output_tokens" in r.usage
    ]
    if tokens:
        agg["mean_total_tokens"] = mean(tokens)
    agg["completed"] = len(ok) / len(results) if results else 0.0
    return agg


def to_markdown(results: list[CaseResult]) -> str:
    keys = sorted({k for r in results for k in r.scores})
    rows = ["| case | " + " | ".join(keys) + " | error |", "|" + "---|" * (len(keys) + 2)]
    for r in results:
        cells = [f"{r.scores[k]:.2f}" if k in r.scores else "-" for k in keys]
        rows.append(f"| {r.case_id} | " + " | ".join(cells) + f" | {r.error or ''} |")
    agg = aggregate(results)
    rows.append("| **mean** | " + " | ".join(f"{agg.get(k, 0):.2f}" for k in keys) + " | |")
    return "\n".join(rows)
