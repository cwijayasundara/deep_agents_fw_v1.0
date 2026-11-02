"""Contract: langgraph config access, trace policy helpers, and callback payload split."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.config import get_config
from langgraph.types import TracePolicy, omit_payload

pytestmark = pytest.mark.contract


def test_get_config_raises_runtime_error_outside_a_run() -> None:
    with pytest.raises(RuntimeError):
        get_config()


def test_trace_policy_and_omit_payload_drop_the_payload() -> None:
    policy = TracePolicy(process_inputs=omit_payload, process_outputs=omit_payload)
    assert policy.process_inputs is not None
    assert policy.process_inputs({"messages": ["secret"]}) == {}
    assert TracePolicy().process_outputs is None


class _Recorder(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.start: dict[UUID, dict[str, Any]] = {}
        self.end: dict[UUID, tuple[LLMResult, dict[str, Any]]] = {}

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self.start[run_id] = kwargs

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        self.end[run_id] = (response, kwargs)


async def test_usage_reaches_on_llm_end_and_metadata_only_chat_model_start() -> None:
    usage = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    model = GenericFakeChatModel(messages=iter([AIMessage(content="x", usage_metadata=usage)]))
    rec = _Recorder()
    await model.ainvoke(
        "hi", config={"callbacks": [rec], "metadata": {"tenant": "acme", "user_id": "u7"}}
    )

    assert rec.start.keys() == rec.end.keys()
    (run_id,) = rec.end
    response, end_kwargs = rec.end[run_id]
    generation = response.generations[0][0]
    assert isinstance(generation, ChatGeneration)
    assert isinstance(generation.message, AIMessage)
    assert generation.message.usage_metadata == usage
    assert "metadata" not in end_kwargs
    assert rec.start[run_id]["metadata"]["tenant"] == "acme"
