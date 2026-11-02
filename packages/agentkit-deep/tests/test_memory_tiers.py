"""Memory tiers on InMemoryStore: /memories/ per user, /org/ read-only per tenant, skills kept."""

from pathlib import Path
from typing import Any

import pytest
from agentkit_deep import build_deep_agent
from agentkit_deep.memory import MEMORY_SOURCES, memory_backend
from agentkit_deep.skills_mount import skills_permissions, skills_routes, skills_source
from agentkit_deep.testing import ScriptedChatModel, ctx, memory_persistence, tool_call
from deepagents.backends import CompositeBackend, StateBackend
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from pydantic import Field

USER_NS = ("default", "agentkit", "platform", "u1", "memories")
ORG_NS = ("default", "agentkit", "platform", "global", "org")
FILE = {"encoding": "utf-8"}
SKILL_MD = "---\nname: alpha\ndescription: Alpha skill for alpha work\n---\n\n# Alpha\n"


class Recording(ScriptedChatModel):
    prompts: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        self.prompts.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def recording(*messages: AIMessage) -> Recording:
    return Recording(messages=iter(messages))


def write(path: str, content: str, id: str = "w") -> AIMessage:
    return tool_call("write_file", {"file_path": path, "content": content}, id)


def system(model: Recording, call: int = 0) -> str:
    return "\n".join(str(m.content) for m in model.prompts[call] if m.type == "system")


async def run(agent: Any, user: str = "u1", thread: str = "t") -> dict[str, Any]:
    return await agent.ainvoke(
        {"messages": [HumanMessage("go")]},
        context=ctx(user_id=user, thread_id=thread),
        config={"configurable": {"thread_id": thread}},
    )


def tool_texts(out: dict[str, Any]) -> list[str]:
    return [str(m.content) for m in out["messages"] if isinstance(m, ToolMessage)]


async def test_memories_write_lands_in_the_user_namespace() -> None:
    p = memory_persistence()
    agent = build_deep_agent(
        model=recording(write("/memories/AGENTS.md", "likes tea"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    await run(agent)
    item = await p.store.aget(USER_NS, "/AGENTS.md")
    assert item is not None and item.value["content"] == "likes tea"


async def test_org_write_is_denied_naming_the_path_and_nothing_is_stored() -> None:
    p = memory_persistence()
    agent = build_deep_agent(
        model=recording(write("/org/AGENTS.md", "pwned"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    out = await run(agent)
    (err,) = tool_texts(out)
    assert "/org/AGENTS.md" in err and "permission" in err.lower()
    assert await p.store.asearch(("default",), limit=100) == []


async def test_subagents_inherit_the_org_write_deny() -> None:
    p = memory_persistence()
    sub_model = recording(write("/org/AGENTS.md", "pwned"), AIMessage(content="sub done"))
    main = recording(
        tool_call("task", {"description": "write org", "subagent_type": "sub"}, "t1"),
        AIMessage(content="ok"),
    )
    agent = build_deep_agent(
        model=main,
        system_prompt="p",
        persistence=p,
        subagents=[{"name": "sub", "description": "d", "system_prompt": "s", "model": sub_model}],
    )
    await run(agent)
    assert sub_model.prompts, "subagent never ran"
    assert await p.store.asearch(("default",), limit=100) == []


async def test_two_users_do_not_see_each_others_memories() -> None:
    p = memory_persistence()
    writer = build_deep_agent(
        model=recording(write("/memories/AGENTS.md", "u1 secret"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    await run(writer, user="u1", thread="a")
    reader_model = recording(
        tool_call("read_file", {"file_path": "/memories/AGENTS.md"}, "r"), AIMessage(content="ok")
    )
    reader = build_deep_agent(model=reader_model, system_prompt="p", persistence=p)
    out = await run(reader, user="u2", thread="b")
    assert "u1 secret" not in system(reader_model)
    assert not any("u1 secret" in t for t in tool_texts(out))


async def test_a_user_named_global_cannot_reach_org_memory() -> None:
    p = memory_persistence()
    await p.store.aput(ORG_NS, "/AGENTS.md", {**FILE, "content": "ORG NOTE"})
    agent = build_deep_agent(
        model=recording(write("/memories/AGENTS.md", "spoof"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    await run(agent, user="global")
    org = await p.store.aget(ORG_NS, "/AGENTS.md")
    assert org is not None and org.value["content"] == "ORG NOTE"


async def test_both_agents_md_sources_reach_agent_memory_org_first() -> None:
    p = memory_persistence()
    await p.store.aput(ORG_NS, "/AGENTS.md", {**FILE, "content": "ORG NOTE"})
    await p.store.aput(USER_NS, "/AGENTS.md", {**FILE, "content": "USER NOTE"})
    model = recording(AIMessage(content="ok"))
    await run(build_deep_agent(model=model, system_prompt="p", persistence=p))
    text = system(model)
    block = text[text.index("<agent_memory>") : text.index("</agent_memory>")]
    assert block.index("ORG NOTE") < block.index("USER NOTE")
    assert MEMORY_SOURCES == ("/org/AGENTS.md", "/memories/AGENTS.md")


async def test_a_memory_written_in_one_thread_is_recalled_in_a_new_thread() -> None:
    p = memory_persistence()
    first = build_deep_agent(
        model=recording(write("/memories/AGENTS.md", "prefers metric"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    await run(first, thread="one")
    model = recording(AIMessage(content="ok"))
    await run(build_deep_agent(model=model, system_prompt="p", persistence=p), thread="two")
    assert "prefers metric" in system(model)


async def test_report_stays_in_ephemeral_state_files() -> None:
    p = memory_persistence()
    agent = build_deep_agent(
        model=recording(write("/report.md", "# R"), AIMessage(content="ok")),
        system_prompt="p",
        persistence=p,
    )
    out = await run(agent)
    assert "/report.md" in out["files"]
    assert await p.store.asearch(("default",), limit=100) == []


async def test_persistence_resumes_a_thread_across_turns() -> None:
    p = memory_persistence()
    model = recording(AIMessage(content="first"), AIMessage(content="second"))
    agent = build_deep_agent(model=model, system_prompt="p", persistence=p)
    await run(agent, thread="r")
    out = await run(agent, thread="r")
    humans = [m for m in out["messages"] if m.type == "human"]
    assert len(humans) == 2 and out["messages"][-1].content == "second"


def test_memory_backend_absorbs_skills_routes_in_one_composite(tmp_path: Path) -> None:
    d = tmp_path / "alpha"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    backend = memory_backend(skills_routes({"main": [d]}))
    assert isinstance(backend, CompositeBackend) and isinstance(backend.default, StateBackend)
    assert set(backend.routes) == {"/skills/main/", "/org/", "/memories/"}
    assert "Alpha" in backend.read("/skills/main/alpha/SKILL.md").file_data["content"]  # type: ignore[index]


def test_memory_backend_rejects_a_skills_route_shadowing_memory() -> None:
    with pytest.raises(ValueError, match="/org/"):
        memory_backend({"/org/": StateBackend()})


async def test_persistent_agent_keeps_its_skills_and_both_write_denies(tmp_path: Path) -> None:
    d = tmp_path / "alpha"
    d.mkdir()
    (d / "SKILL.md").write_text(SKILL_MD)
    p = memory_persistence()
    model = recording(
        write("/skills/main/alpha/SKILL.md", "pwned", "w1"),
        write("/org/AGENTS.md", "pwned", "w2"),
        AIMessage(content="ok"),
    )
    agent = build_deep_agent(
        model=model,
        system_prompt="p",
        persistence=p,
        skills=[skills_source("main")],
        backend=memory_backend(skills_routes({"main": [d]})),
        permissions=skills_permissions(),
    )
    out = await run(agent)
    assert "- **alpha**:" in system(model)
    errors = tool_texts(out)
    assert len(errors) == 2 and all("permission" in e.lower() for e in errors)
    assert (d / "SKILL.md").read_text() == SKILL_MD
    assert await p.store.asearch(("default",), limit=100) == []


def test_persistence_rejects_a_backend_without_memory_routes() -> None:
    with pytest.raises(ValueError, match="memory_backend"):
        build_deep_agent(
            model=recording(AIMessage(content="ok")),
            system_prompt="p",
            persistence=memory_persistence(),
            backend=StateBackend(),
        )


def test_persistence_and_explicit_checkpointer_are_exclusive() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    with pytest.raises(ValueError, match="persistence"):
        build_deep_agent(
            model=recording(AIMessage(content="ok")),
            system_prompt="p",
            persistence=memory_persistence(),
            checkpointer=InMemorySaver(),
        )
