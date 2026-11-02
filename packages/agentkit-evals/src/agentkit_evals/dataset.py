from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ExpectCall(BaseModel):
    """The tool call a single-step case expects. `name` and each arg value are regexes
    matched with `re.search` (against the name, and against `str(arg)`)."""

    name: str
    args: dict[str, str] = Field(default_factory=dict)


class EvalCase(BaseModel):
    id: str
    question: str
    must_cover: list[str] = Field(default_factory=list)  # facts a good report includes (full)
    tags: list[str] = Field(default_factory=list)
    expect_tools: list[str] = Field(default_factory=lambda: ["web_search"])
    min_sources: int = 1
    kind: Literal["full", "single_step"] = "full"
    # single_step: the whole conversation up to the decision point, as {role, content} turns
    # (assistant turns may carry tool_calls, tool turns a tool_call_id). When given it replaces
    # the bare `question` turn, so a decision after tool results can be set up faithfully.
    messages: list[dict[str, Any]] = Field(default_factory=list)
    expect_call: ExpectCall | None = None
    ideal_tool_calls: int | None = None

    @model_validator(mode="after")
    def _kind_requirements(self) -> EvalCase:
        if self.kind == "full" and not self.must_cover:
            raise ValueError("must_cover needs at least one item for a full case")
        if self.kind == "single_step" and self.expect_call is None:
            raise ValueError("a single_step case needs expect_call")
        return self


def load_dataset(path: str | Path) -> list[EvalCase]:
    cases = [
        EvalCase.model_validate_json(line)
        for line in Path(path).read_text().splitlines()
        if line.strip()
    ]
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids")
    return cases


def select_cases(
    cases: list[EvalCase], ids: Iterable[str] = (), tags: Iterable[str] = ()
) -> list[EvalCase]:
    """Cases whose id is in `ids` or that carry any of `tags`, in dataset order.

    No filters keeps every case. An unknown id, or filters that match nothing, is a ValueError."""
    want_ids, want_tags = set(ids), set(tags)
    if not (want_ids or want_tags):
        return cases
    unknown = sorted(want_ids - {c.id for c in cases})
    if unknown:
        raise ValueError(f"unknown case ids: {unknown}")
    picked = [c for c in cases if c.id in want_ids or want_tags & set(c.tags)]
    if not picked:
        raise ValueError(f"no cases match tags {sorted(want_tags)}")
    return picked
