"""Contract: deepagents store routing, memory loading, runtime shape, and harness profiles."""

from __future__ import annotations

from typing import Any

import pytest
from agentkit_deep.testing import ScriptedChatModel, scripted, tool_call
from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field

pytestmark = pytest.mark.contract

HI: Any = {"messages": [{"role": "user", "content": "hi"}]}


class Ctx(BaseModel):
    tenant: str
    user_id: str


def _user_ns(rt: Runtime[Ctx]) -> tuple[str, ...]:
    return ("tenants", rt.context.tenant, "users", rt.context.user_id, "memories")


def _org_ns(rt: Runtime[Ctx]) -> tuple[str, ...]:
    return ("tenants", rt.context.tenant, "global", "org")


class _Recording(GenericFakeChatModel):
    """Scripted model that records the prompt of every call."""

    prompts: list[list[BaseMessage]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> _Recording:
        return self

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.prompts.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


async def test_store_namespace_factory_reads_context_and_write_lands_there() -> None:
    store = InMemoryStore()
    seen: list[tuple[object, object]] = []

    def ns(rt: Runtime[Ctx]) -> tuple[str, ...]:
        seen.append((rt.context, rt.server_info))
        return _user_ns(rt)

    backend = CompositeBackend(
        default=StateBackend(), routes={"/memories/": StoreBackend(namespace=ns)}
    )
    model = scripted(
        tool_call("write_file", {"file_path": "/memories/note.md", "content": "hello"}, "c1"),
        AIMessage(content="done"),
    )
    agent = create_deep_agent(model, backend=backend, store=store, context_schema=Ctx)
    ctx = Ctx(tenant="acme", user_id="u7")
    await agent.ainvoke(HI, context=ctx)

    assert seen, "namespace factory never ran"
    assert all(c is ctx for c, _ in seen)
    assert all(server_info is None for _, server_info in seen)
    item = await store.aget(("tenants", "acme", "users", "u7", "memories"), "/note.md")
    assert item is not None
    assert item.value["content"] == "hello"
    assert await store.asearch(("tenants", "other"), limit=100) == []


async def test_memory_middleware_loads_two_sources_into_agent_memory() -> None:
    store = InMemoryStore()
    file = {"encoding": "utf-8"}
    await store.aput(("tenants", "acme", "global", "org"), "/AGENTS.md", {**file, "content": "ORG"})
    await store.aput(
        ("tenants", "acme", "users", "u7", "memories"), "/AGENTS.md", {**file, "content": "USR"}
    )
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/org/": StoreBackend(namespace=_org_ns),
            "/memories/": StoreBackend(namespace=_user_ns),
        },
    )
    model = _Recording(messages=iter([AIMessage(content="done")]))
    agent = create_deep_agent(
        model,
        backend=backend,
        store=store,
        context_schema=Ctx,
        memory=["/org/AGENTS.md", "/memories/AGENTS.md"],
    )
    await agent.ainvoke(HI, context=Ctx(tenant="acme", user_id="u7"))

    system = str(model.prompts[0][0].content)
    start, end = system.index("<agent_memory>"), system.index("</agent_memory>")
    block = system[start:end]
    assert block.index("ORG") < block.index("USR")


class _ContractProviderModel(ScriptedChatModel):
    """Reports a provider name no real integration uses, so the profile stays local."""

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> Any:
        return {"ls_provider": "agentkit-contract", "ls_model_type": "chat"}


def _bound_tools(model: BaseChatModel) -> set[str]:
    agent = create_deep_agent(model)
    agent.invoke(HI)
    assert isinstance(model, ScriptedChatModel)
    return set(model.bound[0])


def test_harness_profile_excluded_tools_remove_tools_from_bound_set() -> None:
    baseline = _bound_tools(scripted(AIMessage(content="done")))
    assert {"delete", "glob", "task"} <= baseline

    register_harness_profile(
        "agentkit-contract", HarnessProfile(excluded_tools=frozenset({"delete", "glob", "task"}))
    )
    profiled = _bound_tools(_ContractProviderModel(messages=iter([AIMessage(content="done")])))

    assert profiled == baseline - {"delete", "glob", "task"}
