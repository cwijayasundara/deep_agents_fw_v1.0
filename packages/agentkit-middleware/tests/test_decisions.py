import json

import httpx
import pytest
import respx
from agentkit_middleware import (
    CircuitBreaker,
    DecisionsClient,
    DecisionsError,
    DecisionsSelector,
    DecisionsUsage,
    ToolCard,
    Unavailable,
)

URL = "https://api.openai.com/v1/decisions"
CARDS = [
    ToolCard("web_search", "search the web"),
    ToolCard("fetch_url", "fetch a page"),
    ToolCard("sql", "run sql"),
]


async def nosleep(_):
    return None


def client(**kw):
    return DecisionsClient("sk-test", sleep=nosleep, **kw)


def resp(answers):
    return httpx.Response(200, json={"answers": answers, "usage": {"input_tokens": 1}})


def pred(name, p):
    return {"type": "predicate", "name": f"tool:{name}", "probability": p}


def tier(choice, conf=0.9):
    return {
        "type": "choice",
        "name": "model_tier",
        "choice": choice,
        "confidence": conf,
        "probabilities": [{"value": choice, "probability": conf}],
    }


@respx.mock
async def test_request_shape():
    route = respx.post(URL).mock(return_value=resp([tier("default")]))
    sel = DecisionsSelector(client(), always_include=["fetch_url"])
    await sel.select("find x", CARDS, thread_id="th-1")
    req = route.calls[0].request
    body = json.loads(req.content)
    assert req.headers["authorization"] == "Bearer sk-test"
    assert body["model"] == "gpt-6-luna" and body["prompt_cache_key"] == "th-1"
    names = [q["name"] for q in body["questions"]]
    assert names == ["tool:web_search", "tool:sql", "model_tier"]  # always_include not asked
    assert body["questions"][0]["type"] == "predicate"
    tier_q = body["questions"][-1]
    assert [c["value"] for c in tier_q["choices"]] == ["fast", "default", "strong"]
    assert body["input"].index("<tool_catalog>") < body["input"].index("find x")  # stable first


@respx.mock
async def test_answers_matched_by_name_not_position_and_threshold():
    respx.post(URL).mock(
        return_value=resp([tier("strong"), pred("sql", 0.1), pred("web_search", 0.9)])
    )
    out = await DecisionsSelector(client()).select("q", CARDS)
    assert out.tier == "strong"
    assert out.tool_names == {
        "web_search",
        "fetch_url",
    }  # fetch_url unanswered -> kept; sql dropped


@respx.mock
async def test_refusal_keeps_tool_and_low_confidence_keeps_default_tier():
    respx.post(URL).mock(
        return_value=resp(
            [
                {"type": "refusal", "name": "tool:sql"},
                pred("web_search", 0.0),
                pred("fetch_url", 0.0),
                tier("strong", conf=0.2),
            ]
        )
    )
    out = await DecisionsSelector(client()).select("q", CARDS)
    assert out.tool_names == {"sql"} and out.tier == "default"


@respx.mock
async def test_unknown_tier_value_ignored():
    respx.post(URL).mock(return_value=resp([tier("galaxy-brain")]))
    assert (await DecisionsSelector(client()).select("q", CARDS)).tier == "default"


@respx.mock
async def test_max_tools_caps_by_probability_keeping_always():
    respx.post(URL).mock(
        return_value=resp([pred("web_search", 0.6), pred("sql", 0.9), tier("default")])
    )
    out = await DecisionsSelector(client(), max_tools=2, always_include=["fetch_url"]).select(
        "q", CARDS
    )
    assert out.tool_names == {"fetch_url", "sql"}


@respx.mock
async def test_more_than_399_tools_only_asks_399_keeps_rest():
    route = respx.post(URL).mock(return_value=resp([tier("default")]))
    many = [ToolCard(f"t{i}", "d") for i in range(450)]
    out = await DecisionsSelector(client()).select("q", many)
    assert len(json.loads(route.calls[0].request.content)["questions"]) == 400
    assert len(out.tool_names) == 450  # unanswered -> all kept


@respx.mock
async def test_retries_5xx_then_succeeds():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(429), resp([tier("fast")])]
    )
    out = await DecisionsSelector(client()).select("q", CARDS)
    assert out.tier == "fast" and route.call_count == 3


@respx.mock
async def test_4xx_not_retried():
    route = respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(DecisionsError):
        await DecisionsSelector(client()).select("q", CARDS)
    assert route.call_count == 1


@respx.mock
async def test_breaker_opens_then_short_circuits():
    route = respx.post(URL).mock(return_value=httpx.Response(500))
    c = client(breaker=CircuitBreaker(failure_threshold=3, reset_timeout=999), attempts=3)
    with pytest.raises(Unavailable):
        await c.decide("x", [{"type": "predicate", "name": "a", "instructions": "i"}])
    assert route.call_count == 3
    with pytest.raises(Unavailable):
        await c.decide("x", [{"type": "predicate", "name": "a", "instructions": "i"}])
    assert route.call_count == 3  # breaker open: no new request


async def test_question_bounds():
    with pytest.raises(ValueError):
        await client().decide("x", [])


# Real /v1/decisions responses recorded live on 2026-11-02 (T9), replayed through the selector.
FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def live(name):
    return httpx.Response(200, json=json.loads((FIXTURES / name).read_text()))


@respx.mock
async def test_live_response_orchestrator_prompt():
    # tier answer 'fast' at confidence 0.27 < floor 0.5 -> stays on default; sql dropped
    respx.post(URL).mock(return_value=live("decisions_live_orchestrator.json"))
    sel = await DecisionsSelector(client(), default_tier="default").select("q", CARDS)
    assert sel.tier == "default"
    assert sel.tool_names == {"web_search", "fetch_url"}


@respx.mock
async def test_live_response_vague_prompt_drops_all_tools():
    # Known risk: with a vague system prompt Decisions rates every tool ~0 and hides them all.
    respx.post(URL).mock(return_value=live("decisions_live_short_prompt.json"))
    sel = await DecisionsSelector(client(), default_tier="default").select("q", CARDS)
    assert sel.tool_names == set()
    assert sel.tier == "fast"


@respx.mock
async def test_live_response_usage_is_returned_with_the_selection():
    respx.post(URL).mock(return_value=live("decisions_live_short_prompt.json"))
    sel = await DecisionsSelector(client()).select("q", CARDS)
    assert sel.usage == DecisionsUsage(input_tokens=686, output_tokens=0, cached_input_tokens=0)


@respx.mock
async def test_missing_or_malformed_usage_is_none():
    respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": []}))
    assert (await DecisionsSelector(client()).select("q", CARDS)).usage is None
    respx.post(URL).mock(
        return_value=httpx.Response(200, json={"answers": [], "usage": {"input_tokens": "x"}})
    )
    assert (await DecisionsSelector(client()).select("q", CARDS)).usage is None


@respx.mock
async def test_clients_without_explicit_breaker_share_one_per_process():
    """A new client per `load_agent` must not reset the breaker (eval builds one agent per case)."""
    route = respx.post(URL).mock(return_value=httpx.Response(500))
    q = [{"type": "predicate", "name": "a", "instructions": "i"}]
    for _ in range(2):  # 2 agents x 3 attempts = 6 failures >= threshold 5
        with pytest.raises(Unavailable):
            await client(attempts=3).decide("x", q)
    calls = route.call_count
    with pytest.raises(Unavailable):
        await client().decide("x", q)  # a third, fresh client sees the open breaker
    assert route.call_count == calls


async def test_explicit_breaker_is_not_shared():
    a, b = CircuitBreaker(), CircuitBreaker()
    assert client(breaker=a)._breaker is a and client(breaker=b)._breaker is b
    assert client()._breaker is client()._breaker
