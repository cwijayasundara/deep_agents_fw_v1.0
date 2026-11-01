from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from statistics import mean

from .dataset import EvalCase
from .judge import Judge
from .metrics import citation_scores


@dataclass
class RunResult:
    report: str
    retrieved: str  # concatenated tool output the agent actually saw


@dataclass
class CaseResult:
    case_id: str
    scores: dict[str, float] = field(default_factory=dict)
    error: str | None = None


AgentRunner = Callable[[str], Awaitable[RunResult]]


async def _one(case: EvalCase, run_agent: AgentRunner, judge: Judge) -> CaseResult:
    try:
        r = await run_agent(case.question)
        if not r.report.strip():
            return CaseResult(case.id, error="empty report")
        scores = citation_scores(r.report, r.retrieved)
        scores.update(await judge(case, r.report, r.retrieved))
        return CaseResult(case.id, scores)
    except Exception as e:  # one bad case must not sink the run
        return CaseResult(case.id, error=f"{type(e).__name__}: {e}")


async def run_eval(
    cases: list[EvalCase], run_agent: AgentRunner, judge: Judge, concurrency: int = 2
) -> list[CaseResult]:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(c: EvalCase) -> CaseResult:
        async with sem:
            return await _one(c, run_agent, judge)

    return list(await asyncio.gather(*(guarded(c) for c in cases)))


def aggregate(results: list[CaseResult]) -> dict[str, float]:
    ok = [r for r in results if r.error is None]
    keys = sorted({k for r in ok for k in r.scores})
    agg = {k: mean(r.scores[k] for r in ok) for k in keys} if ok else {}
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
