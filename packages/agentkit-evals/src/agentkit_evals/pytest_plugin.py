"""pytest plugin: dataset-driven agent evals (`pytest11` entry point `agentkit`).

    @pytest.mark.agentkit_eval(dataset="evals/steps.jsonl", agent="agent.yaml", kind="single_step")
    def test_steps(case, agentkit_run):
        assert_case(agentkit_run(case), step_pass=1.0)

One test per dataset line (ids are the case ids). Every such test is skipped unless
`--agentkit-live` is given, because it calls a real model. A full run needs a judge model: the
`strong` tier of the `anthropic` registry entry, like `research-eval --judge anthropic`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from .dataset import EvalCase, load_dataset
from .judge import LLMJudge
from .runner import CaseResult, RunResult, run_eval
from .single_step import StepResult, single_step

MARKER = "agentkit_eval"
SKIP_REASON = "live eval; pass --agentkit-live"
DEFAULT_MODEL = "fireworks-glm"
JUDGE_ENTRY = "anthropic"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("agentkit")
    group.addoption(
        "--agentkit-live", action="store_true", help="run agentkit_eval tests (call real models)"
    )
    group.addoption(
        "--agentkit-model",
        default=DEFAULT_MODEL,
        metavar="ENTRY",
        help=f"registry entry the agent under test runs on (default {DEFAULT_MODEL})",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{MARKER}(dataset, agent, kind): dataset-driven agent eval, one test per case "
        "(live: skipped without --agentkit-live)",
    )


def _marker_args(metafunc_or_item: Any) -> dict[str, Any] | None:
    m = metafunc_or_item.definition.get_closest_marker(MARKER)
    if m is None:
        return None
    return {"kind": "full", **m.kwargs}


def _resolve(path: str, test_file: Path, rootdir: Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    for base in (test_file.parent, rootdir):
        if (base / p).exists():
            return base / p
    return test_file.parent / p


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    args = _marker_args(metafunc)
    if args is None or "case" not in metafunc.fixturenames:
        return
    if "dataset" not in args:
        raise pytest.UsageError(f"{metafunc.function.__name__}: {MARKER} needs dataset=")
    path = _resolve(args["dataset"], Path(str(metafunc.definition.path)), metafunc.config.rootpath)
    cases = [c.model_copy(update={"kind": args["kind"]}) for c in load_dataset(path)]
    metafunc.parametrize("case", cases, ids=[c.id for c in cases])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--agentkit-live"):
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if item.get_closest_marker(MARKER) is not None:
            item.add_marker(skip)


def _run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion, also from inside a running event loop (async tests)."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def load_graph(agent: str | Path, model: str) -> tuple[Any, Any]:
    """`(graph, spec)` for the agent YAML on registry entry `model`. A seam for tests."""
    from agentkit_config import load_agent
    from agentkit_core import Settings

    loaded = load_agent(agent, settings=Settings(), overrides={"model": model})
    return loaded.graph, loaded.spec


def load_judge() -> Any:
    from agentkit_core import ModelRegistry, Settings, get_model

    settings = Settings()
    spec = ModelRegistry.default().resolve(JUDGE_ENTRY, "strong")
    return LLMJudge(get_model(spec, settings))


def _context(spec: Any) -> Any:
    from agentkit_core import PlatformContext, Settings

    return PlatformContext(
        tenant=Settings().deployment_tenant,
        product="agentkit",
        team="platform",
        user_id=f"eval-{uuid.uuid4().hex[:8]}",
        thread_id=str(uuid.uuid4()),
        agent_name=spec.name,
        agent_version=spec.version,
    )


async def _run_case(case: EvalCase, agent: str | Path, model: str) -> CaseResult:
    """One case on a freshly loaded agent and a fresh thread (no persistence)."""
    from agentkit_config import read_output
    from langchain_core.messages import HumanMessage

    async def run_step(c: EvalCase) -> StepResult:
        graph, spec = load_graph(agent, model)
        ctx = _context(spec)
        config = {"recursion_limit": 1_000, "configurable": {"thread_id": ctx.thread_id}}
        return await single_step(graph, c, config=config, context=ctx)

    async def run_agent(question: str) -> RunResult:
        graph, spec = load_graph(agent, model)
        ctx = _context(spec)
        config = {"recursion_limit": 1_000, "configurable": {"thread_id": ctx.thread_id}}
        res = await graph.ainvoke(
            {"messages": [HumanMessage(question)]}, config=config, context=ctx
        )
        calls = [
            tc["name"] for m in res["messages"] if m.type == "ai" for tc in (m.tool_calls or [])
        ]
        retrieved = "\n".join(str(m.content) for m in res["messages"] if m.type == "tool")
        return RunResult(
            report=read_output(res, spec.output), retrieved=retrieved, tool_calls=calls
        )

    judge = load_judge() if case.kind == "full" else None
    [result] = await run_eval([case], run_agent, judge, concurrency=1, run_step=run_step)  # type: ignore[arg-type]
    return result


@pytest.fixture
def agentkit_run(request: pytest.FixtureRequest) -> Callable[[EvalCase], CaseResult]:
    """`agentkit_run(case) -> CaseResult`: load the marked agent (on `--agentkit-model`), run the
    case on a fresh thread as the marker's `kind`, and return the scored result."""
    marker = request.node.get_closest_marker(MARKER)
    args = {"kind": "full", **(marker.kwargs if marker else {})}
    if "agent" not in args:
        raise pytest.UsageError(f"{request.node.name}: {MARKER} needs agent=")
    agent = _resolve(args["agent"], Path(str(request.node.path)), request.config.rootpath)
    model = request.config.getoption("--agentkit-model")

    def run(case: EvalCase) -> CaseResult:
        return _run_sync(_run_case(case.model_copy(update={"kind": args["kind"]}), agent, model))

    return run


def assert_case(result: CaseResult, **floors: float) -> None:
    """Fail unless the case ran without error and every named score is at least its floor."""
    scores = ", ".join(f"{k}={v:.2f}" for k, v in sorted(result.scores.items())) or "none"
    head = f"case {result.case_id}: scores [{scores}]"
    if result.error:
        pytest.fail(f"{head}; error: {result.error}", pytrace=False)
    missing = [k for k in floors if k not in result.scores]
    low = [
        f"{k}={result.scores[k]:.2f} < {f}"
        for k, f in floors.items()
        if k in result.scores and result.scores[k] < f
    ]
    if missing or low:
        why = "; ".join([*low, *(f"{k} not scored" for k in missing)])
        reason = f"; reason: {result.reason}" if result.reason else ""
        pytest.fail(f"{head}; below floor: {why}{reason}", pytrace=False)
