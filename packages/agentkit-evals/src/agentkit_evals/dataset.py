from __future__ import annotations

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
