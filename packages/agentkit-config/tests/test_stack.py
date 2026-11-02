from __future__ import annotations

from pathlib import Path
from typing import Any

import agentkit_config.resolve as resolve_mod
from agentkit_config import CodePools, Library, load_agent
from agentkit_config.stack import order_stack
from agentkit_core import Settings
from agentkit_deep.testing import ScriptedChatModel, scripted
from agentkit_middleware import Selection, SelectionMiddleware
from langchain.agents.middleware import AgentMiddleware, ModelFallbackMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatResult

SETTINGS = Settings(_env_file=None, deployment_tenant="default")


class A(AgentMiddleware):
    pass


class B(AgentMiddleware):
    pass


def _items(*names: str) -> list[tuple[str, AgentMiddleware]]:
    out = []
    for n in names:
        mw = A()
        mw.tag = n  # type: ignore[attr-defined]
        out.append((n.split("#")[0], mw))
    return out


def _tags(mws: list[AgentMiddleware]) -> list[str]:
    return [m.tag for m in mws]  # type: ignore[attr-defined]


def test_order_stack_canonical() -> None:
    items = _items(
        "pii", "call_limit", "model_fallback", "custom_a", "selection", "model_retry", "custom_b"
    )
    assert _tags(order_stack(items)) == [
        "selection",
        "model_fallback",
        "model_retry",
        "call_limit",
        "pii",
        "custom_a",
        "custom_b",
    ]


def test_order_stack_is_stable_for_repeats() -> None:
    items = _items("pii#1", "call_limit", "pii#2")
    assert _tags(order_stack(items)) == ["call_limit", "pii#1", "pii#2"]


class Failing(ScriptedChatModel):
    calls: int = 0

    async def _agenerate(self, *a: Any, **k: Any) -> ChatResult:
        self.calls += 1
        raise RuntimeError("boom")

    def _generate(self, *a: Any, **k: Any) -> ChatResult:
        self.calls += 1
        raise RuntimeError("boom")


class StubSelector:
    async def select(self, task: str, tools: list[Any], *, thread_id: str | None = None):
        return Selection("strong", frozenset())


def _pools() -> CodePools:
    return CodePools.from_entry_points().override(
        middleware={
            "model_fallback": lambda ctx, **kw: ModelFallbackMiddleware(
                scripted(AIMessage("from fallback"))
            )
        }
    )


def _agent(tmp_path: Path, middleware: list[str], extra: str = "") -> Path:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "main.md").write_text("I am {{agent_name}}.")
    lines = "".join(f"  - {m}\n" for m in middleware)
    p = tmp_path / "agent.yaml"
    p.write_text(
        "apiVersion: agentkit/v1\nkind: Agent\nname: demo\nmodel: anthropic\nprompt: main\n"
        f"output: null\nmiddleware:\n{lines}{extra}"
    )
    return p


RETRY = "{type: model_retry, params: {max_retries: 1, initial_delay: 0}}"
FALLBACK = "{type: model_fallback}"
LIMIT = "{type: call_limit, params: {max_model_calls: 5}}"


async def test_retry_then_fallback_answers_from_fallback(tmp_path: Path) -> None:
    primary = Failing(messages=iter([]))
    p = _agent(tmp_path, [RETRY, FALLBACK])  # reverse of canonical order
    loaded = load_agent(
        p, settings=SETTINGS, library=Library.from_roots([tmp_path], _pools()), model=primary
    )
    out = await loaded.graph.ainvoke(
        {"messages": [HumanMessage("hi")]},
        context={
            "tenant": "default",
            "product": "agentkit",
            "team": "platform",
            "user_id": "local",
            "thread_id": "t",
            "agent_name": "demo",
            "agent_version": "0",
        },
    )
    assert out["messages"][-1].content == "from fallback"
    assert primary.calls == 2


async def test_fallback_inside_selection(tmp_path: Path, monkeypatch) -> None:
    strong = Failing(messages=iter([]))
    monkeypatch.setattr(
        resolve_mod,
        "decisions_middleware",
        lambda *a, **k: SelectionMiddleware(StubSelector(), models={"strong": strong}),
    )
    p = _agent(tmp_path, [FALLBACK], "selection: decisions\n")
    loaded = load_agent(
        p,
        settings=SETTINGS,
        library=Library.from_roots([tmp_path], _pools()),
        model=Failing(messages=iter([])),
    )
    out = await loaded.graph.ainvoke(
        {"messages": [HumanMessage("hi")]},
        context={
            "tenant": "default",
            "product": "agentkit",
            "team": "platform",
            "user_id": "local",
            "thread_id": "t2",
            "agent_name": "demo",
            "agent_version": "0",
        },
    )
    assert out["messages"][-1].content == "from fallback"
    assert strong.calls >= 1


def test_yaml_file_order_no_longer_matters(tmp_path: Path, monkeypatch) -> None:
    import agentkit_config.load as load_mod

    seen: list[list[str]] = []

    def rec(**kw: Any) -> Any:
        seen.append([type(m).__name__ for m in kw["middleware"]])
        return object()

    monkeypatch.setattr(load_mod, "build_deep_agent", rec)
    for order in ([RETRY, FALLBACK, LIMIT], [LIMIT, FALLBACK, RETRY]):
        d = tmp_path / str(len(seen))
        d.mkdir()
        load_agent(
            _agent(d, order),
            settings=SETTINGS,
            library=Library.from_roots([d], _pools()),
            model=scripted(),
        )
    assert seen[0] == seen[1]
    assert seen[0][:3] == [
        "ModelFallbackMiddleware",
        "ModelRetryMiddleware",
        "ModelCallLimitMiddleware",
    ]
