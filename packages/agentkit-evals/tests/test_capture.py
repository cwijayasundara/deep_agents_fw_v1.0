import hashlib
from uuid import uuid4

from agentkit_deep import build_deep_agent
from agentkit_deep.testing import ctx, scripted, tool_call
from agentkit_evals import RequestCapture, digest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


async def test_capture_records_each_model_call():
    cap = RequestCapture()
    model = scripted(
        tool_call("write_file", {"file_path": "/a.md", "content": "x"}, "1"),
        AIMessage(content="done"),
    )
    agent = build_deep_agent(model=model, system_prompt="p")
    await agent.ainvoke(
        {"messages": [HumanMessage("go")]}, config={"callbacks": [cap]}, context=ctx()
    )
    assert len(cap.records) == 2
    assert all(r.namespace == "" for r in cap.records)
    assert cap.records[1].message_count > cap.records[0].message_count


async def test_capture_reads_model_and_tools_from_invocation_params():
    cap = RequestCapture()
    await cap.on_chat_model_start(
        {},
        [[SystemMessage("s"), HumanMessage("q")]],
        run_id=uuid4(),
        metadata={"checkpoint_ns": "", "langgraph_step": 3},
        invocation_params={
            "model": "m-1",
            "tools": [{"type": "function", "function": {"name": "web_search"}}],
        },
    )
    r = cap.records[0]
    assert r.model == "m-1" and r.tools == ("web_search",) and r.step == 3
    assert r.system_sha == hashlib.sha256(b"s").hexdigest()
    assert r.message_count == 1


def test_digest_is_order_and_content_sensitive():
    a, b = HumanMessage("a"), AIMessage("b")
    assert digest([a, b]) != digest([b, a])
    assert digest([a, b]) == digest([HumanMessage("a"), AIMessage("b")])
