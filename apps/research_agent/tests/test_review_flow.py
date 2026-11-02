from typing import Any

import agentkit_config.resolve as resolve_mod
import pytest
from agentkit_config import CodePools
from agentkit_config.cli import main as agentkit_main
from agentkit_config.flow.compile import flow_library, load_flow
from agentkit_core import Settings
from agentkit_deep.testing import ScriptedChatModel, tool_call
from agentkit_tools import Page, Source, make_fetch_tool, make_web_search_tool
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from research_agent.flow_nodes import REVIEW_FLOW, critique, needs_rework

GOOD = "# R\nX is true [1]\n\n## Sources\n[1] https://a.example/x"
BAD = "# R\nX is true."


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact about x")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def fake_pools() -> CodePools:
    return CodePools.from_entry_points().override(
        tools={
            "web_search": lambda ctx, **kw: make_web_search_tool(FakeSearch()),
            "fetch_url": lambda ctx, **kw: make_fetch_tool(FakeFetch()),
        }
    )


class RecordingModel(ScriptedChatModel):
    """Scripted model that records the messages it receives on each call."""

    received: list[list[BaseMessage]] = []

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.received.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def two_round_model() -> RecordingModel:
    """Round 1 writes a report without citations; round 2 (after critique) cites [1]."""
    return RecordingModel(
        messages=iter(
            [
                tool_call("write_file", {"file_path": "/report.md", "content": BAD}, "1"),
                AIMessage(content="done"),
                tool_call("write_file", {"file_path": "/report.md", "content": GOOD}, "2"),
                AIMessage(content="done"),
            ]
        ),
        received=[],
    )


@pytest.fixture(autouse=True)
def no_decisions(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shipped agent uses `selection: decisions`; keep the Decisions API offline."""
    monkeypatch.setattr(resolve_mod, "decisions_middleware", lambda *a, **k: AgentMiddleware())


def build(model: RecordingModel) -> Any:
    return load_flow(
        REVIEW_FLOW,
        settings=Settings(_env_file=None, openai_api_key="o", fireworks_api_key="f"),
        library=flow_library(REVIEW_FLOW, fake_pools()),
        model=model,
        checkpointer=InMemorySaver(),
    )


async def test_review_flow_runs_offline() -> None:
    graph = build(two_round_model())
    cfg = {"configurable": {"thread_id": "t1"}}
    paused = await graph.ainvoke({"question": "what is x?"}, cfg)
    assert paused["__interrupt__"][0].value == {"node": "review"}
    assert paused["rounds"] == 2 and paused["critique"] == ""
    # LangGraph quirk: an empty dict is read as an empty resume *map* (interrupt id -> value),
    # so `Command(resume={})` answers nothing and the flow stays paused at review.
    still = await graph.ainvoke(Command(resume={}), cfg)
    assert still["__interrupt__"][0].value == {"node": "review"}
    done = await graph.ainvoke(Command(resume={"critique": ""}), cfg)  # reviewer approves
    assert "[1]" in done["draft"] and "Sources" in done["draft"]
    assert "__interrupt__" not in done


async def test_agent_node_multi_field_message() -> None:
    model = two_round_model()
    graph = build(model)
    await graph.ainvoke({"question": "what is x?"}, {"configurable": {"thread_id": "t2"}})
    firsts = [msgs[-1] for msgs in model.received if msgs[-1].type == "human"]
    assert len(firsts) == 2  # one fresh agent run per research round
    round1, round2 = (str(m.content) for m in firsts)
    assert round1 == "## question\nwhat is x?"
    assert round2.startswith("## question\nwhat is x?\n\n## critique\n")
    assert critique({"draft": BAD})["critique"] in round2


def test_critique_and_router() -> None:
    assert critique({"draft": GOOD}) == {"critique": "", "rounds": 1}
    bad = critique({"draft": BAD, "rounds": 1})
    assert bad["rounds"] == 2 and "[1]" in bad["critique"] and "Sources" in bad["critique"]
    assert needs_rework({"critique": "fix", "rounds": 1}) == "rework"
    assert needs_rework({"critique": "fix", "rounds": 2}) == "ok"
    assert needs_rework({"critique": "", "rounds": 1}) == "ok"


def test_flow_file_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert agentkit_main(["validate", str(REVIEW_FLOW)]) == 0
    assert "0 error(s)" in capsys.readouterr().out
