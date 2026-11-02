from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from openevals.llm import create_llm_as_judge

from .dataset import EvalCase

log = logging.getLogger(__name__)

# Retrieved text includes subagent fetches, so it is large; ~30k tokens keeps the judge in budget.
MAX_CONTEXT_CHARS = 120_000
_ATTEMPTS = 3


class JudgeError(RuntimeError):
    """The judge model never returned a numeric score."""


def _score(name: str, evaluator: Callable[..., Any], **kwargs: Any) -> float:
    """Judges sometimes reply without a score; retry rather than failing the whole case."""
    last: Any = None
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            last = evaluator(**kwargs)
        except KeyError as e:  # openevals indexes response["score"] itself
            last = f"KeyError: {e}"
        score = last.get("score") if isinstance(last, dict) else None
        if isinstance(score, int | float):
            return float(score)
        log.warning("%s judge returned no score (attempt %d/%d)", name, attempt, _ATTEMPTS)
    raise JudgeError(f"{name} judge returned no score after {_ATTEMPTS} attempts: {last!r:.200}")


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
        # Opus 5.5 rejects forced tool calling (openevals' default), and a reply without the
        # tool call fails the case; Anthropic's native json_schema output has no such gap.
        kw = {"method": "json_schema"} if type(model).__name__ == "ChatAnthropic" else None
        self._g = create_llm_as_judge(
            prompt=GROUNDED,
            feedback_key="groundedness",
            judge=model,
            continuous=True,
            structured_output_kwargs=kw,
        )
        self._c = create_llm_as_judge(
            prompt=COMPLETE,
            feedback_key="completeness",
            judge=model,
            continuous=True,
            structured_output_kwargs=kw,
        )

    async def __call__(self, case: EvalCase, report: str, retrieved: str) -> dict[str, float]:
        def run() -> dict[str, float]:
            g = _score(
                "groundedness", self._g, outputs=report, context=retrieved[:MAX_CONTEXT_CHARS]
            )
            c = _score(
                "completeness",
                self._c,
                inputs=case.question,
                outputs=report,
                reference_outputs="; ".join(case.must_cover),
            )
            return {"groundedness": g, "completeness": c}

        return await asyncio.to_thread(run)
