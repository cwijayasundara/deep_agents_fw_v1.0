from __future__ import annotations

import asyncio
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from openevals.llm import create_llm_as_judge

from .dataset import EvalCase

GROUNDED = """Judge whether every factual claim in the report is supported by the retrieved
source material. 1 = fully supported, 0 = unsupported or fabricated claims.

<report>{outputs}</report>
<retrieved_sources>{context}</retrieved_sources>"""

COMPLETE = """Judge whether the report answers the question and covers each required point.
1 = answers fully and covers all points, 0 = misses the question.

<question>{inputs}</question>
<required_points>{reference_outputs}</required_points>
<report>{outputs}</report>"""


class Judge(Protocol):
    async def __call__(self, case: EvalCase, report: str, retrieved: str) -> dict[str, float]: ...


class LLMJudge:
    """LLM-as-judge via openevals. `model` is any chat model, so the judge provider is config."""

    def __init__(self, model: BaseChatModel) -> None:
        self._g = create_llm_as_judge(
            prompt=GROUNDED, feedback_key="groundedness", judge=model, continuous=True
        )
        self._c = create_llm_as_judge(
            prompt=COMPLETE, feedback_key="completeness", judge=model, continuous=True
        )

    async def __call__(self, case: EvalCase, report: str, retrieved: str) -> dict[str, float]:
        def run() -> dict[str, float]:
            g: Any = self._g(outputs=report, context=retrieved[:30_000])
            c: Any = self._c(
                inputs=case.question, outputs=report, reference_outputs="; ".join(case.must_cover)
            )
            return {"groundedness": float(g["score"]), "completeness": float(c["score"])}

        return await asyncio.to_thread(run)
