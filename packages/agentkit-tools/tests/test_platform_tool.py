from __future__ import annotations

import pytest
from agentkit_core import BuildContext, ModelRegistry, Settings
from agentkit_tools import ToolMeta, check_tool_contract, platform_tool, tool_meta
from agentkit_tools.factories import fetch_url, web_search
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError


@pytest.fixture
def ctx() -> BuildContext:
    settings = Settings(_env_file=None)  # type: ignore[arg-type]
    return BuildContext(settings, ModelRegistry.default().resolve(), "agent")


def test_version_must_be_semver() -> None:
    with pytest.raises(ValidationError):
        ToolMeta(owner="platform", version="1.x", side_effects="read")


def test_decorator_attaches_meta_and_factory_still_builds() -> None:
    @platform_tool(owner="platform", version="1.0.0", side_effects="read", tenants=["a", "b"])
    def factory(ctx: object) -> str:
        return "built"

    meta = tool_meta(factory)
    assert meta is not None
    assert meta.owner == "platform"
    assert meta.tenants == frozenset({"a", "b"})
    assert meta.identity == "service"
    assert meta.classification == "internal"
    assert factory(None) == "built"


def test_tool_meta_is_none_for_undecorated() -> None:
    assert tool_meta(lambda ctx: None) is None


def _tool(description: str, schema: type[BaseModel], name: str = "t") -> BaseTool:
    async def run(**kwargs: object) -> str:
        return ""

    return StructuredTool.from_function(
        coroutine=run, name=name, description=description, args_schema=schema
    )


def test_contract_reports_empty_description() -> None:
    class Args(BaseModel):
        q: str = Field(description="query")

    problems = check_tool_contract(_tool("", Args))
    assert "empty description" in problems


def test_contract_reports_undescribed_argument() -> None:
    class Args(BaseModel):
        q: str

    assert "argument 'q' has no description" in check_tool_contract(_tool("Does a thing.", Args))


@pytest.mark.parametrize("arg", ["tenant", "tenant_id", "user", "user_id", "thread_id"])
def test_contract_rejects_identity_args(arg: str) -> None:
    schema = type(
        "Args", (BaseModel,), {"__annotations__": {arg: str}, arg: Field(description="x")}
    )
    assert f"argument '{arg}' must come from runtime context" in check_tool_contract(
        _tool("Does a thing.", schema)
    )


def test_clean_tool_passes() -> None:
    class Args(BaseModel):
        q: str = Field(description="query")

    assert check_tool_contract(_tool("Does a thing.", Args)) == []


def test_shipped_tools_pass_and_are_decorated(ctx: BuildContext) -> None:
    for factory in (web_search, fetch_url):
        meta = tool_meta(factory)
        assert meta is not None
        assert meta.version == "1.0.0"
        assert meta.side_effects == "external"
        assert meta.classification == "public"
        assert check_tool_contract(factory(ctx)) == []
