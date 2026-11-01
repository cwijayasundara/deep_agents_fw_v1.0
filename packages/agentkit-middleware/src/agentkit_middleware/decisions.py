"""OpenAI Decisions API (`POST /v1/decisions`, model `gpt-6-luna`) client and Selector.

Schema: docs/reference/openai-decisions-api.md. Anything that doc marks "not documented"
(rate limits, timeouts, refusal fields) is handled defensively, not assumed.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import httpx

from .resilience import CircuitBreaker, call_with_retry
from .selection import Selection, ToolCard

DECISIONS_URL = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
MAX_QUESTIONS = 400

DEFAULT_TIERS: Mapping[str, str] = {
    "fast": "Simple lookup, short answer, little reasoning or synthesis.",
    "default": "Typical multi-step task needing some planning and synthesis.",
    "strong": "Hard, open-ended task needing deep reasoning or long synthesis.",
}


class DecisionsError(RuntimeError):
    """Non-retryable API error (e.g. 400/401)."""


class _Retryable(RuntimeError):
    """429 / 5xx / transport failure."""


class DecisionsClient:
    def __init__(
        self,
        api_key: str,
        *,
        url: str = DECISIONS_URL,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
        breaker: CircuitBreaker | None = None,
        attempts: int = 3,
        base: float = 0.5,
        cap: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._key, self._url = api_key, url
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._breaker = breaker or CircuitBreaker()
        self._retry: dict[str, Any] = {"attempts": attempts, "base": base, "cap": cap}
        self._sleep, self._rng = sleep, rng

    async def decide(
        self, input_: str, questions: Sequence[dict[str, Any]], cache_key: str | None = None
    ) -> dict[str, Any]:
        """Parsed response. Raises `Unavailable` (breaker/retries) or `DecisionsError` (4xx)."""
        if not 1 <= len(questions) <= MAX_QUESTIONS:
            raise ValueError(f"questions must be 1-{MAX_QUESTIONS}, got {len(questions)}")
        body: dict[str, Any] = {"model": MODEL, "input": input_, "questions": list(questions)}
        if cache_key:
            body["prompt_cache_key"] = cache_key

        async def once() -> dict[str, Any]:
            try:
                resp = await self._client.post(
                    self._url, headers={"Authorization": f"Bearer {self._key}"}, json=body
                )
            except httpx.TransportError as e:
                raise _Retryable(type(e).__name__) from e
            if resp.status_code == 429 or resp.status_code >= 500:
                raise _Retryable(f"HTTP {resp.status_code}")
            if resp.status_code >= 400:
                raise DecisionsError(f"HTTP {resp.status_code}")
            data: dict[str, Any] = resp.json()
            return data

        return await call_with_retry(
            once,
            breaker=self._breaker,
            retry_on=(_Retryable,),
            sleep=self._sleep,
            rng=self._rng,
            **self._retry,
        )


class DecisionsSelector:
    """Selector backed by one batched Decisions request per thread."""

    def __init__(
        self,
        client: DecisionsClient,
        *,
        tiers: Mapping[str, str] = DEFAULT_TIERS,
        default_tier: str = "default",
        threshold: float = 0.5,
        max_tools: int | None = None,
        always_include: Sequence[str] = (),
        confidence_floor: float = 0.5,
        system_prompt: str = "",
    ) -> None:
        if default_tier not in tiers:
            raise ValueError(f"default_tier '{default_tier}' not in tiers")
        self._c, self._tiers, self._default = client, dict(tiers), default_tier
        self._threshold, self._max = threshold, max_tools
        self._always, self._floor = frozenset(always_include), confidence_floor
        self._system = system_prompt

    def _build(
        self, task: str, tools: list[ToolCard]
    ) -> tuple[str, list[dict[str, Any]], set[str]]:
        asked = [t for t in tools if t.name not in self._always][: MAX_QUESTIONS - 1]
        # Stable content first so the shared prefix is cacheable (>=1,024 tokens); task last.
        catalog = "\n".join(f"- {t.name}: {t.description}" for t in tools)
        input_ = (
            f"<system>\n{self._system}\n</system>\n<tool_catalog>\n{catalog}\n</tool_catalog>\n"
            f"<request>\n{task}\n</request>"
        )
        questions: list[dict[str, Any]] = [
            {
                "type": "predicate",
                "name": f"tool:{t.name}",
                "instructions": f"Will the agent likely need the tool `{t.name}` for this request?",
            }
            for t in asked
        ]
        questions.append(
            {
                "type": "choice",
                "name": "model_tier",
                "instructions": "Which model tier does this request need?",
                "choices": [{"value": k, "description": v} for k, v in self._tiers.items()],
            }
        )
        return input_, questions, {t.name for t in asked}

    async def select(
        self, task: str, tools: list[ToolCard], *, thread_id: str | None = None
    ) -> Selection:
        input_, questions, asked = self._build(task, tools)
        resp = await self._c.decide(input_, questions, cache_key=thread_id)
        answers = {
            a.get("name"): a for a in resp.get("answers", []) if isinstance(a, dict)
        }  # by name

        scored: dict[str, float] = {}
        for t in tools:
            if t.name in self._always or t.name not in asked:
                scored[t.name] = 1.0  # never asked -> keep
                continue
            a = answers.get(f"tool:{t.name}", {})
            p = a.get("probability") if a.get("type") == "predicate" else None
            scored[t.name] = float(p) if isinstance(p, int | float) else 1.0  # refusal -> keep
        keep = {n for n, p in scored.items() if p >= self._threshold or n in self._always}
        if self._max is not None and len(keep) > self._max:
            ranked = sorted(keep - self._always, key=lambda n: scored[n], reverse=True)
            keep = set(self._always & keep) | set(ranked[: max(self._max - len(self._always), 0)])

        tier = self._default
        a = answers.get("model_tier", {})
        if a.get("type") == "choice" and a.get("choice") in self._tiers:
            conf = a.get("confidence")
            if isinstance(conf, int | float) and conf >= self._floor:
                tier = a["choice"]
        return Selection(tier, frozenset(keep))
