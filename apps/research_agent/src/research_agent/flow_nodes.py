"""Code pools for the research_with_review flow: its state schema, critique node and router."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, TypedDict

REVIEW_FLOW = Path(__file__).parents[2] / "flows" / "research_with_review.yaml"
MAX_ROUNDS = 2


class ReviewState(TypedDict, total=False):
    question: str
    draft: str
    critique: str
    rounds: int


def critique(state: ReviewState) -> dict[str, str | int]:
    """Deterministic check: the draft cites `[1]` and has a Sources section."""
    draft = state.get("draft", "")
    problems = []
    if "[1]" not in draft:
        problems.append("Cite your claims inline with numbered markers like [1].")
    if "Sources" not in draft:
        problems.append("End with a 'Sources' section listing each cited URL.")
    return {"critique": "\n".join(problems), "rounds": state.get("rounds", 0) + 1}


def needs_rework(state: ReviewState) -> Literal["rework", "ok"]:
    if state.get("critique") and state.get("rounds", 0) < MAX_ROUNDS:
        return "rework"
    return "ok"
