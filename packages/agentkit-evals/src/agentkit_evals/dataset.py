from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    id: str
    question: str
    must_cover: list[str] = Field(min_length=1)  # facts/points a good report includes
    tags: list[str] = Field(default_factory=list)
    expect_tools: list[str] = Field(default_factory=lambda: ["web_search"])
    min_sources: int = 1


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
