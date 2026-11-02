import pytest
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_middleware.factories import (
    call_limit,
    model_fallback,
    model_retry,
    pii,
    tool_call_limit,
    tool_retry,
)
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)


def _ctx(**kw):
    return BuildContext(Settings(_env_file=None, **kw), ModelRegistry.default().resolve(), "a")


def test_call_limit_builds_model_call_limit():
    mw = call_limit(_ctx(), max_model_calls=7)
    assert isinstance(mw, ModelCallLimitMiddleware) and mw.run_limit == 7


def test_call_limit_passes_thread_limit_and_exit_behavior():
    mw = call_limit(_ctx(), max_model_calls=7, thread_limit=20, exit_behavior="error")
    assert mw.run_limit == 7 and mw.thread_limit == 20 and mw.exit_behavior == "error"


def test_tool_call_limit_builds():
    mw = tool_call_limit(_ctx(), run_limit=3, tool_name="web_search", thread_limit=9)
    assert isinstance(mw, ToolCallLimitMiddleware)
    assert (mw.run_limit, mw.thread_limit, mw.tool_name) == (3, 9, "web_search")
    assert mw.exit_behavior == "continue"


def test_model_fallback_resolves_entries_and_tiers():
    ctx = _ctx(fireworks_api_key="f", anthropic_api_key="a")
    mw = model_fallback(ctx, models=["fireworks-deepseek", "anthropic:strong"])
    assert isinstance(mw, ModelFallbackMiddleware)
    assert [getattr(m, "model_name", None) or m.model for m in mw.models] == [
        "accounts/fireworks/models/deepseek-v4p1-flash-1017",
        "claude-opus-5-5",
    ]


def test_model_fallback_missing_key_is_config_error():
    with pytest.raises(ConfigError):
        model_fallback(_ctx(), models=["anthropic"])


def test_model_fallback_rejects_empty_and_bad_tier():
    with pytest.raises(ConfigError):
        model_fallback(_ctx(), models=[])
    with pytest.raises(ConfigError, match="unknown tier 'bogus'"):
        model_fallback(_ctx(anthropic_api_key="a"), models=["anthropic:bogus"])
    with pytest.raises(ConfigError, match="unknown model entry 'nope'"):
        model_fallback(_ctx(), models=["nope"])


@pytest.mark.parametrize("item", ["", ":strong", "a:b:c", "anthropic:"])
def test_model_fallback_rejects_malformed_items(item):
    with pytest.raises(ConfigError, match="bad model item"):
        model_fallback(_ctx(anthropic_api_key="a"), models=[item])


@pytest.mark.parametrize(
    "call",
    [
        lambda c: call_limit(c, max_model_calls=3, exit_behavior="boom"),
        lambda c: call_limit(c, max_model_calls=0),
        lambda c: call_limit(c, max_model_calls=None),
        lambda c: tool_call_limit(c, run_limit=None),
        lambda c: call_limit(c, max_model_calls=3, thread_limit=-1),
        lambda c: tool_call_limit(c, run_limit=0),
        lambda c: tool_call_limit(c, run_limit=2, thread_limit=0),
        lambda c: model_retry(c, max_retries=-1),
        lambda c: tool_retry(c, max_retries=-1),
        lambda c: model_retry(c, initial_delay=-1.0),
        lambda c: pii(c, type="email", strategy="shred"),
    ],
)
def test_bad_params_raise_config_error(call):
    with pytest.raises(ConfigError):
        call(_ctx())


def test_model_retry_raises_on_final_failure():
    mw = model_retry(_ctx(), max_retries=3)
    assert isinstance(mw, ModelRetryMiddleware)
    assert mw.on_failure == "error" and mw.max_retries == 3


def test_tool_retry_builds():
    mw = tool_retry(_ctx(), tools=["web_search"])
    assert isinstance(mw, ToolRetryMiddleware)
    assert mw.on_failure == "continue" and mw.max_retries == 2


def test_pii_builds_per_type():
    mw = pii(_ctx(), type="email")
    assert isinstance(mw, PIIMiddleware) and mw.name == "PIIMiddleware[email]"


def test_pii_rejects_url_type():
    with pytest.raises(ConfigError, match="citations"):
        pii(_ctx(), type="url")


def test_pii_rejects_unknown_type():
    with pytest.raises(ConfigError):
        pii(_ctx(), type="ssn-ish")
