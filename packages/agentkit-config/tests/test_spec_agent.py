from pathlib import Path

import pytest
from agentkit_config.errors import SpecErrors
from agentkit_config.spec import ToolRef, parse_agent, parse_subagent

FULL = """\
apiVersion: agentkit/v1
kind: Agent
name: research_agent
description: Deep-research agent that writes a cited report.
version: 0.1.0
tags: [research]

model: fireworks-glm        # ModelRegistry entry; override with --model
tier: default               # fast | default | strong
selection: decisions        # optional; omit = all tools, fixed tier

prompt: research/orchestrator          # PromptRegistry name
tools:
  - web_search
  - fetch_url: {max_chars: 20000}      # name, or {name: params}
skills: [citations]                    # SkillRegistry names
subagents:
  - researcher                         # SubagentRegistry name
  - name: critic                       # or inline, same shape as a subagent file
    description: Checks a draft report for unsupported claims.
    prompt: research/critic
    tools: [fetch_url]
middleware:
  - type: call_limit
    params: {max_model_calls: 40}
    enabled: true                      # format kept from the old builder
output: /report.md                     # file the CLI/eval treat as the result
"""

MIN = "apiVersion: agentkit/v1\nkind: Agent\nname: a\nmodel: m\nprompt: p\n"


def write(tmp_path: Path, text: str) -> Path:
    f = tmp_path / "agent.yaml"
    f.write_text(text)
    return f


def paths(exc: pytest.ExceptionInfo[SpecErrors]) -> list[str]:
    return [e.path for e in exc.value.errors]


def test_parses_full_example(tmp_path: Path) -> None:
    spec = parse_agent(write(tmp_path, FULL))
    assert spec.tools[0] == ToolRef("web_search", {})
    assert spec.tools[1] == ToolRef("fetch_url", {"max_chars": 20000})
    assert spec.subagents[0] == "researcher"
    assert not isinstance(spec.subagents[1], str)
    assert spec.subagents[1].name == "critic"
    assert spec.subagents[1].tools == [ToolRef("fetch_url", {})]
    assert spec.middleware[0].params == {"max_model_calls": 40}
    assert spec.selection == "decisions"


def test_unknown_key_reports_path(tmp_path: Path) -> None:
    with pytest.raises(SpecErrors) as exc:
        parse_agent(write(tmp_path, MIN + "toolz: [x]\n"))
    assert "toolz" in paths(exc)
    assert exc.value.errors[0].file.endswith("agent.yaml")


def test_bad_nested_path(tmp_path: Path) -> None:
    with pytest.raises(SpecErrors) as exc:
        parse_agent(write(tmp_path, MIN + "subagents: [{name: x}]\n"))
    assert sorted(paths(exc)) == ["subagents[0].description", "subagents[0].prompt"]


def test_bad_tool_in_inline_subagent(tmp_path: Path) -> None:
    text = MIN + "subagents:\n  - name: x\n    description: d\n    prompt: p\n    tools: [1]\n"
    with pytest.raises(SpecErrors) as exc:
        parse_agent(write(tmp_path, text))
    assert any(p.startswith("subagents[0].tools[0]") for p in paths(exc))


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "key: [unclosed\n"])
def test_bad_files_raise_spec_errors(tmp_path: Path, text: str) -> None:
    f = write(tmp_path, text)
    with pytest.raises(SpecErrors) as exc:
        parse_agent(f)
    assert exc.value.errors[0].file == str(f)


def test_wrong_kind(tmp_path: Path) -> None:
    with pytest.raises(SpecErrors) as exc:
        parse_agent(write(tmp_path, MIN.replace("kind: Agent", "kind: Flow")))
    assert "kind" in paths(exc)


def test_parse_subagent_and_api_version(tmp_path: Path) -> None:
    ok = parse_subagent(write(tmp_path, "kind: SubAgent\nname: s\ndescription: d\nprompt: p\n"))
    assert ok.apiVersion == "agentkit/v1"
    with pytest.raises(SpecErrors) as exc:
        parse_subagent(write(tmp_path, "apiVersion: x/v2\nname: s\ndescription: d\nprompt: p\n"))
    assert "apiVersion" in paths(exc)


def test_raise_if_errors_and_warnings() -> None:
    from agentkit_config.errors import SpecError

    w = SpecError("f", "p", "m", "warning")
    SpecErrors([w]).raise_if_errors()
    assert SpecErrors([w]).warnings == [w]
    assert str(w) == "f:p: m"
