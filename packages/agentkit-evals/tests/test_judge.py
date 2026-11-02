import pytest
from agentkit_evals.dataset import EvalCase
from agentkit_evals.judge import MAX_CONTEXT_CHARS, JudgeError, LLMJudge


class Seq:
    """Fake openevals evaluator returning queued results; records the kwargs it saw."""

    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, **kw):
        self.calls.append(kw)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def judge(g, c):
    j = LLMJudge.__new__(LLMJudge)
    j._g, j._c = g, c
    return j


CASE = EvalCase(id="x", question="q?", must_cover=["a"])


async def test_retries_when_score_missing():
    g = Seq({"key": "groundedness", "comment": "no score"}, {"score": 0.5})
    out = await judge(g, Seq({"score": 1.0}))(CASE, "report", "ctx")
    assert out == {"groundedness": 0.5, "completeness": 1.0}
    assert len(g.calls) == 2


async def test_raises_judge_error_after_retries():
    g = Seq(*[{"comment": "nope"}] * 3)
    with pytest.raises(JudgeError, match="groundedness"):
        await judge(g, Seq({"score": 1.0}))(CASE, "report", "ctx")


async def test_context_cap():
    g = Seq({"score": 1.0})
    await judge(g, Seq({"score": 1.0}))(CASE, "r", "x" * (MAX_CONTEXT_CHARS + 10))
    assert len(g.calls[0]["context"]) == MAX_CONTEXT_CHARS
    assert MAX_CONTEXT_CHARS >= 100_000


async def test_retries_when_openevals_raises_keyerror():
    # openevals indexes response["score"] itself when the judge omits it
    g = Seq(KeyError("score"), {"score": 0.7})
    out = await judge(g, Seq({"score": 1.0}))(CASE, "report", "ctx")
    assert out["groundedness"] == 0.7
