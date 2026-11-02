from __future__ import annotations

import re

from .dataset import EvalCase
from .single_step import StepResult

_URL = re.compile(r"https?://[^\s)\]>\"']+")


def extract_urls(text: str) -> set[str]:
    return {u.rstrip(".,;") for u in _URL.findall(text)}


_SOURCES_HEADING = re.compile(r"^#{1,6}\s*Sources\b", re.IGNORECASE | re.MULTILINE)


def sources_section(report: str) -> float:
    """1.0 if the report has a markdown heading named Sources."""
    return 1.0 if _SOURCES_HEADING.search(report) else 0.0


def source_count_ok(report: str, min_sources: int) -> float:
    return 1.0 if len(extract_urls(report)) >= min_sources else 0.0


def tool_recall(expected: list[str], called: list[str]) -> float:
    """Share of the expected tools that were called at least once; 1.0 when none are expected."""
    want = set(expected)
    return len(want & set(called)) / len(want) if want else 1.0


def citation_scores(report: str, retrieved_text: str) -> dict[str, float]:
    """Deterministic: does the report cite, and are cited URLs ones the agent really retrieved?"""
    cited = extract_urls(report)
    retrieved = extract_urls(retrieved_text)
    return {
        "has_citation": 1.0 if cited else 0.0,
        "citation_validity": (len(cited & retrieved) / len(cited)) if cited else 0.0,
    }


def step_failure(case: EvalCase, step: StepResult) -> str | None:
    """Why a single-step decision misses `expect_call`; None when ANY call matches."""
    want = case.expect_call
    if want is None:
        return "case has no expect_call"
    if step.name is None:
        return "no tool call"
    calls = step.calls or [(step.name, step.args)]
    for name, args in calls:
        if re.search(want.name, name) and all(
            k in args and re.search(v, str(args[k])) for k, v in want.args.items()
        ):
            return None
    names = [n for n, _ in calls]
    if not any(re.search(want.name, n) for n in names):
        return f"called {', '.join(names)}, expected {want.name}"
    return f"{want.name} called with args not matching {want.args}: {calls[0][1]}"


def step_pass(case: EvalCase, step: StepResult) -> float:
    """1.0 only when the tool name matches and every expected arg regex matches."""
    return 1.0 if step_failure(case, step) is None else 0.0


def tool_call_ratio(case: EvalCase, calls: list[str]) -> float | None:
    """Calls made over the ideal count (1.0 is ideal, above is wasteful); None without an ideal."""
    if not case.ideal_tool_calls:
        return None
    return len(calls) / case.ideal_tool_calls
