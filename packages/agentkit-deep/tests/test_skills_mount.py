"""Contract tests for the owner-scoped, read-only skills mount (and the factory pass-throughs)."""

from pathlib import Path
from typing import Any

import pytest
from agentkit_deep import build_deep_agent
from agentkit_deep.skills_mount import skills_mount, skills_source
from agentkit_deep.testing import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult
from pydantic import Field

ALPHA_MD = "---\nname: alpha\ndescription: Alpha skill for alpha work\n---\n\n# Alpha\nDo alpha.\n"
BETA_MD = "---\nname: beta\ndescription: Beta skill for beta work\n---\n\n# Beta\nDo beta.\n"


class RecordingModel(ScriptedChatModel):
    """ScriptedChatModel that also records the messages of every model call."""

    seen: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> ChatResult:
        self.seen.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def recording(*messages: AIMessage) -> RecordingModel:
    return RecordingModel(messages=iter(messages))


def system_text(messages: list[BaseMessage]) -> str:
    return "\n".join(str(m.content) for m in messages if m.type == "system")


def listed(skill: str, prompt: str) -> bool:
    """True when SkillsMiddleware listed `skill` in the prompt's skills section."""
    return f"- **{skill}**:" in prompt


@pytest.fixture
def skill_dirs(tmp_path: Path) -> dict[str, Path]:
    dirs = {}
    for name, md in (("alpha", ALPHA_MD), ("beta", BETA_MD)):
        d = tmp_path / "lib" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(md)
        dirs[name] = d
    return dirs


async def test_agent_sees_only_declared_skills(skill_dirs: dict[str, Path]) -> None:
    backend, permissions = skills_mount({"main": [skill_dirs["alpha"]]})
    model = recording(AIMessage(content="done"))
    agent = build_deep_agent(
        model=model,
        system_prompt="MAIN",
        skills=[skills_source("main")],
        backend=backend,
        permissions=permissions,
    )
    await agent.ainvoke({"messages": [HumanMessage("go")]})
    prompt = system_text(model.seen[0])
    assert listed("alpha", prompt)
    assert "/skills/main/alpha/SKILL.md" in prompt
    assert not listed("beta", prompt)
    assert "beta" not in prompt.lower()


async def test_subagent_skills_scoped(skill_dirs: dict[str, Path]) -> None:
    backend, permissions = skills_mount(
        {"main": [skill_dirs["alpha"]], "sub": [skill_dirs["beta"]]}
    )
    model = recording(
        tool_call("task", {"description": "do it", "subagent_type": "sub"}, "t1"),
        AIMessage(content="sub done"),
        AIMessage(content="done"),
    )
    agent = build_deep_agent(
        model=model,
        system_prompt="MAIN",
        subagents=[
            {
                "name": "sub",
                "description": "the sub",
                "system_prompt": "SUBPROMPT",
                "skills": [skills_source("sub")],
            }
        ],
        skills=[skills_source("main")],
        backend=backend,
        permissions=permissions,
    )
    out = await agent.ainvoke({"messages": [HumanMessage("go")]})
    assert out["messages"][-1].content == "done"
    sub_prompts = [system_text(m) for m in model.seen if "SUBPROMPT" in system_text(m)]
    main_prompts = [system_text(m) for m in model.seen if "SUBPROMPT" not in system_text(m)]
    assert len(sub_prompts) == 1
    assert listed("beta", sub_prompts[0])
    assert not listed("alpha", sub_prompts[0])
    assert main_prompts and all(listed("alpha", p) for p in main_prompts)
    assert not any(listed("beta", p) for p in main_prompts)


async def test_skills_read_only(skill_dirs: dict[str, Path]) -> None:
    backend, permissions = skills_mount({"main": [skill_dirs["alpha"]]})
    model = recording(
        tool_call(
            "write_file", {"file_path": "/skills/main/alpha/SKILL.md", "content": "pwned"}, "w1"
        ),
        AIMessage(content="done"),
    )
    agent = build_deep_agent(
        model=model,
        system_prompt="MAIN",
        skills=[skills_source("main")],
        backend=backend,
        permissions=permissions,
    )
    out = await agent.ainvoke({"messages": [HumanMessage("go")]})
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "permission" in str(tool_msgs[0].content).lower()
    assert (skill_dirs["alpha"] / "SKILL.md").read_text() == ALPHA_MD


def test_backend_itself_refuses_writes(skill_dirs: dict[str, Path]) -> None:
    """Read-only holds below the tool layer too (permissions are tool-level only)."""
    backend, _ = skills_mount({"main": [skill_dirs["alpha"]]})
    assert backend.write("/skills/main/alpha/new.md", "x").error
    assert backend.edit("/skills/main/alpha/SKILL.md", "Alpha", "Pwned").error
    assert backend.delete("/skills/main/alpha/SKILL.md").error
    assert backend.upload_files([("/skills/main/alpha/SKILL.md", b"x")])[0].error
    assert (skill_dirs["alpha"] / "SKILL.md").read_text() == ALPHA_MD
    assert not (skill_dirs["alpha"] / "new.md").exists()


def test_mount_lists_owner_skills_and_denies_writes(skill_dirs: dict[str, Path]) -> None:
    backend, permissions = skills_mount(
        {"main": [skill_dirs["alpha"]], "sub": [skill_dirs["beta"]]}
    )
    entries = backend.ls("/skills/main/").entries or []
    assert [(e["path"], e.get("is_dir")) for e in entries] == [("/skills/main/alpha/", True)]
    assert "Do alpha." in backend.read("/skills/main/alpha/SKILL.md").file_data["content"]  # type: ignore[index]
    assert backend.read("/skills/main/beta/SKILL.md").error
    [rule] = permissions
    assert (rule.operations, rule.paths, rule.mode) == (["write"], ["/skills/**"], "deny")


def test_duplicate_skill_name_for_one_owner_is_rejected(tmp_path: Path) -> None:
    a, b = tmp_path / "x" / "alpha", tmp_path / "y" / "alpha"
    for d in (a, b):
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(ALPHA_MD)
    with pytest.raises(ValueError, match="alpha"):
        skills_mount({"main": [a, b]})


async def test_wrong_level_is_caught(skill_dirs: dict[str, Path]) -> None:
    """Pins the silent trap: a skill *dir* as source yields no skills, so the mount always
    hands out the parent level via skills_source."""
    assert skills_source("main") == "/skills/main/"
    backend, permissions = skills_mount({"main": [skill_dirs["alpha"]]})
    model = recording(AIMessage(content="done"))
    agent = build_deep_agent(
        model=model,
        system_prompt="MAIN",
        skills=["/skills/main/alpha/"],
        backend=backend,
        permissions=permissions,
    )
    await agent.ainvoke({"messages": [HumanMessage("go")]})
    prompt = system_text(model.seen[0])
    assert not listed("alpha", prompt)
    assert "No skills available" in prompt
