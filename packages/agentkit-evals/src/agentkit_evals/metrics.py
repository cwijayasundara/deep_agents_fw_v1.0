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
    """Why a single-step decision misses the case's `expect_call`; None when it matches."""
    want = case.expect_call
    if want is None:
        return "case has no expect_call"
    if step.name is None:
        return "no tool call"
    if not re.search(want.name, step.name):
        return f"called {step.name}, expected {want.name}"
    for arg, pattern in want.args.items():
        if arg not in step.args:
            return f"{step.name} is missing arg {arg}"
        if not re.search(pattern, str(step.args[arg])):
            return f"arg {arg}={step.args[arg]!r} does not match {pattern!r}"
    return None


def step_pass(case: EvalCase, step: StepResult) -> float:
    """1.0 only when the tool name matches and every expected arg regex matches."""
    return 1.0 if step_failure(case, step) is None else 0.0


def tool_call_ratio(case: EvalCase, calls: list[str]) -> float | None:
    """Calls made over the ideal count (1.0 is ideal, above is wasteful); None without an ideal."""
    if not case.ideal_tool_calls:
        return None
    return len(calls) / case.ideal_tool_calls
