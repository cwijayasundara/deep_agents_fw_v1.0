from agentkit_core import BuildContext, ModelRegistry, Settings
from agentkit_middleware.factories import call_limit
from langchain.agents.middleware import ModelCallLimitMiddleware


def test_call_limit_builds_model_call_limit():
    ctx = BuildContext(Settings(_env_file=None), ModelRegistry.default().resolve(), "a")
    mw = call_limit(ctx, max_model_calls=7)
    assert isinstance(mw, ModelCallLimitMiddleware) and mw.run_limit == 7
