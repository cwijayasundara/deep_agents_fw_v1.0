# agentkit declarative agents and flows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build DeepAgents agents and LangGraph flows from YAML files that pick tools, skills, prompts, subagents and middleware from shared pools by name, then rebuild the research agent this way.

**Architecture:** A new `agentkit-config` package with one module per responsibility: pydantic spec models, a generic `Registry[T]`, file-backed pools (prompts, skills, subagents, agents), entry-point-backed code pools (tools, middleware, nodes, schemas), cross-reference validation, resolution to factory kwargs, `load_agent`, and a flow compiler. `build_deep_agent` stays the only caller of `create_deep_agent`.

**Tech Stack:** Python 3.12, uv workspace, pydantic v2, PyYAML, deepagents 0.7.32, langchain 1.4.7, langgraph 1.2.19, pytest + pytest-asyncio, mypy strict, ruff.

**Spec:** `docs/superpowers/specs/2026-11-01-agentkit-declarative-agents-design.md`

## Global Constraints

- **Precondition:** T9 is finished and committed on the Python build before Task 1 starts (spec, "Sequencing"). Work on a branch `declarative-agents`.
- Pins stay in `constraints.txt`. Run everything through `make test` / `make lint`, which set `UV_CONSTRAINT=constraints.txt`. Add no new third-party dependency; pydantic and PyYAML are already in the tree.
- Single responsibility per module, aiming for 200 lines or fewer. No class may parse, resolve and build all at once.
- `agentkit_config/spec/` imports no LangChain, LangGraph or deepagents.
- Every bad reference fails at load time, before any network call. All errors in a file are collected and reported together, each with the file, the YAML path (for example `subagents[1].tools[0]`), the message and the known names.
- Missing API keys are not validation errors. They fail at build.
- YAML header: `apiVersion: agentkit/v1`, plus `kind: Agent | SubAgent | Flow`. Unknown keys are rejected (`extra="forbid"`).
- Prompt variables: only `{{agent_name}}` and `{{date}}`. Any other `{{var}}` is a load error.
- `selection: decisions` is a top-level key and never appears under `middleware:`.
- Subagent `tools` replace the parent's tools. Subagent `skills` are not inherited.
- No MCP, `memory:` section, tenant filtering, versioned prompt refs, UI or REST API.
- Live tests and evals use only the `fireworks-glm` registry entry (user's instruction, 2026-11-02). Other providers are covered offline only.
- Mypy strict and ruff (line length 100) must pass. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A misspelled tool name inside a subagent.** The load fails with `subagents[0].tools[1]`, the bad name and the known tool names, not a deepagents traceback mid-run. Tested in Task 5.
2. **An empty `agent.yaml`, a YAML list, or a YAML syntax error.** Each gives a `SpecErrors` naming the file, not a pydantic or yaml stack trace. Tested in Task 2.
3. **The same prompt, skill or subagent name defined in two library roots.** This is an error naming both files, not a silent shadow. Tested in Task 3.
4. **`--model nope`.** The load fails listing the known registry entries before any key check or network call. Tested in Task 7.
5. **Running the CLI from a directory other than the repo root.** Library roots resolve relative to the agent file, not the current directory. Tested in Task 3 (`Library.for_file`) and Task 8 (CLI).

---

## File map

```
packages/agentkit-core/src/agentkit_core/build_context.py      BuildContext (new)
packages/agentkit-deep/src/agentkit_deep/factory.py            + skills/backend/permissions pass-through
packages/agentkit-deep/src/agentkit_deep/skills_mount.py       owner-scoped read-only skills backend (new)
packages/agentkit-deep/src/agentkit_deep/testing.py            + describe_build()
packages/agentkit-tools/src/agentkit_tools/langchain_tools.py  split into make_web_search_tool / make_fetch_tool
packages/agentkit-tools/src/agentkit_tools/factories.py        web_search / fetch_url pool factories (new)
packages/agentkit-middleware/src/agentkit_middleware/factories.py  call_limit factory (new)
packages/agentkit-config/                                      new package
  src/agentkit_config/spec/{__init__,common,agent,flow}.py
  src/agentkit_config/{errors,registry,library,validate,resolve,selection,output,load,cli}.py
  src/agentkit_config/pools/{__init__,prompts,skills,subagents,agents,code}.py
  src/agentkit_config/flow/{__init__,validate,nodes,compile}.py
libraries/prompts/research/{orchestrator,researcher}.md
libraries/subagents/researcher.yaml
apps/research_agent/agent.yaml
apps/research_agent/flows/research_with_review.yaml
apps/research_agent/src/research_agent/flow_nodes.py           proof-flow state + fns (new)
apps/research_agent/src/research_agent/{agent,cli,eval_cli}.py shrink / switch to load_agent
apps/research_agent/config/*.yaml, prompts.py                  deleted (Task 8)
```

---

### Task 1: Capture the equivalence snapshot from the Python build

**Files:**
- Modify: `packages/agentkit-deep/src/agentkit_deep/testing.py`
- Create: `apps/research_agent/tests/fixtures/python_build_snapshot.json`
- Create: `apps/research_agent/tests/test_snapshot.py`

**Interfaces:**
- Produces: `describe_build(kwargs: Mapping[str, Any]) -> dict[str, Any]` in `agentkit_deep.testing`. It returns `{"name", "system_prompt", "tools": sorted names, "subagents": [{"name", "description", "system_prompt", "tools": sorted names, "skills"}] sorted by name, "middleware": [type(m).__name__ ...], "skills": list | None}`. Task 8 compares the YAML build against this.

- [ ] **Step 1: Write the test.** `test_python_build_matches_snapshot`: monkeypatch `research_agent.agent.build_deep_agent` with a recorder that stores kwargs and returns `object()`. Call `build_research_agent({"model": "anthropic", "tier": "default", "selection": "decisions"}, Settings(_env_file=None, tavily_api_key="t", openai_api_key="o", anthropic_api_key="a"), search=FakeSearch(), fetch=FakeFetch())`. Assert `describe_build(recorded) == json.loads(fixture.read_text())`. If the env var `UPDATE_SNAPSHOT=1` is set, write the fixture instead (sorted keys, indent 2).
- [ ] **Step 2: Run it.** `UPDATE_SNAPSHOT=1 uv run pytest apps/research_agent/tests/test_snapshot.py`, then run it again without the variable. Expect PASS. Check by eye that the fixture has tools `["fetch_url","web_search"]`, one subagent `researcher`, and middleware `["SelectionMiddleware"]`.
- [ ] **Step 3: Commit** `test: snapshot research agent build for YAML equivalence`.

### Task 2: `agentkit-config` package and spec models

**Files:**
- Create: `packages/agentkit-config/pyproject.toml`. Dependencies: `agentkit-core`, `agentkit-deep`, `agentkit-middleware`, `pydantic`, `pyyaml`. Script: `agentkit = "agentkit_config.cli:main"`.
- Modify: root `pyproject.toml` (workspace dependency and source `agentkit-config`).
- Create: `src/agentkit_config/{__init__,py.typed,errors}.py`, `spec/{__init__,common,agent}.py`
- Test: `packages/agentkit-config/tests/test_spec_agent.py`

**Interfaces:**
- Produces, in `errors.py`:
  - `@dataclass(frozen=True) SpecError(file: str, path: str, message: str, severity: Literal["error","warning"] = "error")`. `__str__` gives `"{file}:{path}: {message}"`.
  - `class SpecErrors(Exception)` holding `errors: list[SpecError]`. It provides `.raise_if_errors()` and `.warnings`.
- Produces, in `spec/common.py`:
  - `load_yaml(path: Path) -> dict[str, Any]`. It raises `SpecErrors` when a file is empty, is not a mapping, or has a YAML syntax error.
  - `Ref = str`
  - `NamedParams` parsing, so that `"web_search"` and `{"fetch_url": {"max_chars": 20000}}` both become `ToolRef(name: str, params: dict[str, Any])`.
- Produces, in `spec/agent.py` (pydantic, `extra="forbid"`):
  - `MiddlewareRef(type: str, params: dict = {}, enabled: bool = True)`
  - `SubAgentSpec(apiVersion?, kind: Literal["SubAgent"]="SubAgent", name, description, prompt: str, tools: list[ToolRef]=[], skills: list[str]=[], middleware: list[MiddlewareRef]=[], model: str|None=None, tier: str|None=None, response_schema: str|None=None)`
  - `SubagentEntry = str | SubAgentSpec` (a name, or the inline form)
  - `AgentSpec(apiVersion: Literal["agentkit/v1"], kind: Literal["Agent"], name, description="", version="0.1.0", tags: list[str]=[], model: str, tier: str="default", selection: Literal["decisions"]|None=None, prompt: str, tools: list[ToolRef]=[], skills: list[str]=[], subagents: list[SubagentEntry]=[], middleware: list[MiddlewareRef]=[], output: str|None=None)`
  - `parse_agent(path: Path) -> AgentSpec` and `parse_subagent(path: Path) -> SubAgentSpec`. Both convert pydantic `ValidationError` into `SpecErrors`, joining each error's `loc` into the dotted/indexed path (`subagents[1].tools[0]`).

- [ ] **Step 1: Write failing tests.**
  - `test_parses_full_example`: the spec's illustrative YAML gives `tools[1] == ToolRef("fetch_url", {"max_chars": 20000})` and `subagents[0] == "researcher"`, and `subagents[1].name == "critic"`.
  - `test_unknown_key_reports_path`: a top-level `toolz:` gives a `SpecErrors` containing path `toolz`.
  - `test_bad_nested_path`: `subagents: [{name: x}]` (missing `description` and `prompt`) gives errors whose paths start with `subagents[0]`.
  - `test_empty_file`, `test_list_file` and `test_yaml_syntax_error` each raise `SpecErrors` with `file` set and no pydantic or yaml exception escaping (Review Focus 2).
  - `test_wrong_kind`: `kind: Flow` given to `parse_agent` produces an error.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-config`. Expect FAIL (import error).
- [ ] **Step 3: Implement** the files above. `ToolRef` uses a `model_validator(mode="before")` to accept the bare string or the one-key mapping.
- [ ] **Step 4: Run** `make test`. Expect PASS, with every earlier test still passing.
- [ ] **Step 5: Commit** `feat(config): agent spec models with path-aware errors`.

### Task 3: Registry base and file pools

**Files:**
- Create: `src/agentkit_config/registry.py`, `pools/{__init__,prompts,skills,subagents,agents}.py`, `library.py` (file pools only in this task; code pools are added in Task 4)
- Test: `tests/test_registry.py`, `tests/test_file_pools.py`, `tests/test_library.py`

**Interfaces:**
- `class Registry(Generic[T])`:
  - `__init__(kind: str, entries: Mapping[str, T] = {})`
  - `register(name, value, *, source: str)`. It raises `SpecErrors` on a duplicate, naming both sources (Review Focus 3).
  - `get(name, *, file: str, path: str) -> T`. On an unknown name it raises `SpecErrors` whose message lists the sorted known names.
  - `names() -> list[str]`, `__contains__`
  - `replaced(overrides: Mapping[str, T]) -> Registry[T]`, which returns a new instance.
- `pools/prompts.py`:
  - `PromptRegistry.from_roots(roots: Sequence[Path]) -> Registry[Prompt]`. It scans `<root>/prompts/**/*.md`; the name is the relative path without `.md` (`research/orchestrator`).
  - `@dataclass Prompt(name, text, source)`. Optional `---` front matter is stripped from `text`, and so are trailing newlines (`.rstrip("\n")`), so a prompt file matches the old Python string constant exactly.
  - `variables(text) -> set[str]` using the regex `\{\{\s*(\w+)\s*\}\}`.
  - `render(prompt, *, agent_name: str, date: str) -> str`.
  - `ALLOWED_VARS = {"agent_name", "date"}`.
- `pools/skills.py`: `SkillRegistry.from_roots(roots) -> Registry[Skill]`. It scans `<root>/skills/*/SKILL.md`. `@dataclass Skill(name, dir: Path, tools: frozenset[str])`, where `tools` is the union of front-matter `metadata.include_tools` (a list) and `allowed-tools` (split on whitespace). It is a `SpecErrors` when the front-matter `name` differs from the directory name.
- `pools/subagents.py`: `SubagentRegistry.from_roots(roots) -> Registry[SubAgentSpec]`. It scans `<root>/subagents/*.yaml` with `parse_subagent`. The key is the spec's `name`.
- `pools/agents.py`: `AgentFileRegistry.from_roots(roots) -> Registry[Path]`. It scans `<root>/agents/*.yaml` and `<root>/agent.yaml`, keyed by the parsed `name`.
- `library.py`:
  - `@dataclass(frozen=True) Library(roots: tuple[Path, ...], prompts, skills, subagents, agents, code: CodePools | None = None)`. `code` is set by Task 4.
  - `Library.from_roots(roots, code=None)`
  - `Library.for_file(path: Path, code=None)`. Its roots are, in order: `path.parent`; the nearest ancestor directory named `libraries` found by walking up from `path.parent` (as `<ancestor>/libraries`); then the entries of `AGENTKIT_LIBRARY_PATH` (split on `os.pathsep`). Missing directories are skipped.

- [ ] **Step 1: Write failing tests** using `tmp_path` trees.
  - `test_duplicate_across_roots_is_error`: two roots each have `prompts/a.md`, and the message contains both paths.
  - `test_unknown_lists_known`
  - `test_prompt_name_from_relative_path`
  - `test_prompt_front_matter_stripped`
  - `test_render_vars`: `"hi {{agent_name}} on {{ date }}"` renders correctly.
  - `test_skill_tools_from_metadata_and_allowed_tools`
  - `test_skill_name_mismatch`
  - `test_subagent_pool_keyed_by_name`
  - `test_agent_pool_finds_agent_yaml_and_agents_dir`
  - `test_for_file_independent_of_cwd`: `monkeypatch.chdir(tmp_path / "elsewhere")`, then `Library.for_file(repo/apps/x/agent.yaml)` has roots `[repo/apps/x, repo/libraries]` (Review Focus 5).
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-config`. Expect FAIL.
- [ ] **Step 3: Implement.** Each pool module holds only its scanner and dataclass. Front matter is parsed with `yaml.safe_load` on the block between the leading `---` lines.
- [ ] **Step 4: Run** `make test`. Expect PASS.
- [ ] **Step 5: Commit** `feat(config): generic registry, file-backed pools, library roots`.

### Task 4: BuildContext, tool and middleware factories, code pools

**Files:**
- Create: `packages/agentkit-core/src/agentkit_core/build_context.py` (export it from `agentkit_core`)
- Modify: `packages/agentkit-tools/src/agentkit_tools/langchain_tools.py`. Replace `make_research_tools` with `make_web_search_tool(search) -> BaseTool` and `make_fetch_tool(fetch) -> BaseTool`, keeping the same tool names, docstrings and error-as-text behaviour.
- Create: `packages/agentkit-tools/src/agentkit_tools/factories.py`, `packages/agentkit-middleware/src/agentkit_middleware/factories.py`
- Modify: `pyproject.toml` of agentkit-tools and agentkit-middleware (entry points); `apps/research_agent/src/research_agent/agent.py` (until Task 8 it builds tools with the two new functions)
- Create: `packages/agentkit-config/src/agentkit_config/pools/code.py`
- Test: `packages/agentkit-tools/tests/test_factories.py`, `packages/agentkit-middleware/tests/test_factories.py`, `packages/agentkit-config/tests/test_code_pools.py`

**Interfaces:**
- `@dataclass(frozen=True) BuildContext(settings: Settings, model: ModelSpec, agent_name: str)`
- Pool factory contract: `factory(ctx: BuildContext, **params) -> BaseTool` (tools) and `factory(ctx: BuildContext, **params) -> AgentMiddleware` (middleware).
- `agentkit_tools.duckduckgo.DuckDuckGoSearch` (new file), implementing the existing `SearchTool` protocol (`async search(query, k) -> list[Source]`). It wraps `ddgs.DDGS().text(query, max_results=k)` in `asyncio.to_thread` and maps `href`/`title`/`body` to `Source(url, title, snippet)`. Any `ddgs` exception, including its rate-limit error, is re-raised as `ToolError("search failed: <ExceptionName>")`, so the agent sees error text, not a crash. Add `ddgs==9.16.1` to `constraints.txt` and `ddgs` to agentkit-tools' dependencies.
- `agentkit_tools.factories`:
  - `web_search(ctx, *, backend: Literal["tavily", "duckduckgo"] = "tavily") -> BaseTool`. With `tavily`, it raises `ConfigError("TAVILY_API_KEY is required for the web search tool")` when the key is missing (moved from `research_agent.agent._require`). `duckduckgo` needs no key. An unknown backend raises `ConfigError` listing both values. Selecting by `Literal` means `check_params` doesn't catch a bad value; the factory does, at build time. SearXNG is a later addition, not part of this plan.
  - `fetch_url(ctx, *, max_chars: int = 20_000) -> BaseTool`
- Entry points:
  - `[project.entry-points."agentkit.tools"] web_search = "agentkit_tools.factories:web_search"`, and the same for `fetch_url`
  - `[project.entry-points."agentkit.middleware"] call_limit = "agentkit_middleware.factories:call_limit"`
- `agentkit_middleware.factories.call_limit(ctx, *, max_model_calls: int) -> AgentMiddleware` returns `ModelCallLimitMiddleware(run_limit=max_model_calls)`.
- `pools/code.py`:
  - `@dataclass(frozen=True) CodePools(tools: Registry[ToolFactory], middleware: Registry[MiddlewareFactory], nodes: Registry[Callable[..., Any]], schemas: Registry[type])`
  - `CodePools.from_entry_points()` reads groups `agentkit.tools`, `agentkit.middleware`, `agentkit.nodes` and `agentkit.schemas` via `importlib.metadata.entry_points(group=...)`.
  - `.override(**pools: Mapping[str, Any]) -> CodePools` (`override(tools={"web_search": fake})`)
  - `check_params(factory, params) -> str | None` returns the `TypeError` message from `inspect.signature(factory).bind(None, **params)`, or `None`.

- [ ] **Step 1: Write failing tests.**
  - `test_web_search_requires_tavily_key`
  - `test_web_search_duckduckgo_needs_no_key`: `web_search(ctx, backend="duckduckgo")` builds with `Settings(_env_file=None)`.
  - `test_web_search_unknown_backend`: raises `ConfigError` naming `tavily` and `duckduckgo`.
  - `test_duckduckgo_maps_results`: monkeypatch `ddgs.DDGS.text` to return `[{"href": "https://a.example", "title": "A", "body": "b"}]` and expect `[Source("https://a.example", "A", "b")]`.
  - `test_duckduckgo_error_becomes_tool_error`: a patched `text` raising an exception gives `ToolError`, and the tool returns text starting with `ERROR:`.
  - `test_fetch_url_max_chars_param`: it builds and has the name `fetch_url`.
  - `test_call_limit_builds_model_call_limit`
  - `test_entry_points_registered`: after `make sync`, `CodePools.from_entry_points().tools.names()` includes both tools and `.middleware.names()` includes `call_limit`.
  - `test_override_replaces_only_named`
  - `test_check_params_rejects_unknown_kwarg`
  - Update the existing `agentkit-tools` tests that used `make_research_tools`.
- [ ] **Step 2: Run** `make test`. Expect the new tests to FAIL.
- [ ] **Step 3: Implement, then run `make sync`** so the editable installs pick up the entry points.
- [ ] **Step 4: Run** `make test`. Expect PASS, including Task 1's snapshot test, which proves the tool split changed nothing.
- [ ] **Step 5: Commit** `feat: BuildContext, pool factories for tools/middleware, entry-point code pools`.

### Task 5: Cross-reference validation

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/validate.py`
- Test: `packages/agentkit-config/tests/test_validate.py`

**Interfaces:**
- Consumes: `AgentSpec`, `Library` (with `code`), `ModelRegistry`, `ALLOWED_VARS`, `variables`, `check_params`, and `BUILTIN_TOOLS` from `agentkit_middleware.selection`.
- Produces: `validate_agent(spec: AgentSpec, lib: Library, models: ModelRegistry, *, file: str) -> list[SpecError]`. It never raises; the caller decides.

Rules (each one is a test):
- An unknown model entry or tier, or an unknown prompt, tool, skill, subagent name, middleware type or response schema (top level and in every subagent, inline or from the pool). The path is exact, for example `subagents[0].tools[1]` (Review Focus 1).
- Tool or middleware params rejected by `check_params`.
- A duplicate tool name in one agent or subagent, or a duplicate subagent name.
- A prompt using a variable outside `ALLOWED_VARS`.
- Skills-to-tools: `skill.tools - (owner tool names | BUILTIN_TOOLS)` is non-empty. The error is on `skills[i]` and names the missing tools.
- A subagent without `response_schema` gets a **warning** with the message `"no response_schema; completion contract recommended"`.
- A `middleware` entry with `type: selection` is an error: `"use top-level 'selection:'"`.

- [ ] **Step 1: Write failing tests**, one per rule, against a `tmp_path` library and a `CodePools` built directly with fake factories. Add `test_collects_all_errors`: three independent mistakes give three errors.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-config/tests/test_validate.py`. Expect FAIL.
- [ ] **Step 3: Implement.** Use one small function per rule, with `validate_agent` composing them.
- [ ] **Step 4: Run.** Expect PASS.
- [ ] **Step 5: Commit** `feat(config): load-time cross-reference validation`.

### Task 6: Factory pass-throughs and the owner-scoped skills mount

**Files:**
- Modify: `packages/agentkit-deep/src/agentkit_deep/factory.py`
- Create: `packages/agentkit-deep/src/agentkit_deep/skills_mount.py`
- Test: `packages/agentkit-deep/tests/test_skills_mount.py`

**Interfaces:**
- `build_deep_agent(..., skills: Sequence[str] | None = None, backend: BackendProtocol | None = None, permissions: Sequence[FilesystemPermission] | None = None)` passes these straight to `create_deep_agent`.
- `skills_mount(owners: Mapping[str, Sequence[Path]]) -> tuple[BackendProtocol, list[FilesystemPermission]]`. `owners` maps an owner (the agent name or a subagent name) to its skill directories. The result is a `CompositeBackend(default=StateBackend(), routes=...)` in which `/skills/<owner>/<skill>/` exposes exactly that skill read-only, plus `FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")`. The agent's source is `/skills/<owner>/`, and each subagent's `SubAgent.skills` is `["/skills/<subagent>/"]`. The routing mechanism is the implementer's choice; the tests below fix the behaviour.

- [ ] **Step 1: Write failing contract tests** with two `tmp_path` skills `alpha` and `beta`, using `scripted` models.
  - `test_agent_sees_only_declared_skills`: with owner `main` → `[alpha]`, the system prompt the model receives lists `alpha` and not `beta`. Check `ScriptedChatModel` request messages, or record them via a `wrap_model_call` probe middleware.
  - `test_subagent_skills_scoped`: owner `sub` → `[beta]`. A `task` call into `sub` gives the subagent's prompt `beta` but not `alpha`.
  - `test_skills_read_only`: a scripted `write_file` to `/skills/main/alpha/SKILL.md` returns a permission error and the file on disk is unchanged.
  - `test_wrong_level_is_caught`: a guard against the silent failure the report warns about. If `skills=["/skills/main/alpha/"]` (the skill dir instead of its parent) yields no skills, the test documents that `skills_mount` always emits the parent level.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-deep`. Expect FAIL.
- [ ] **Step 3: Implement** `skills_mount` and the pass-throughs.
- [ ] **Step 4: Run** `make test`. Expect PASS.
- [ ] **Step 5: Commit** `feat(deep): skills/backend/permissions pass-through and owner-scoped skills mount`.

### Task 7: Resolve and `load_agent`

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/{selection,resolve,output,load}.py`
- Test: `packages/agentkit-config/tests/test_load.py`

**Interfaces:**
- `selection.decisions_middleware(ctx: BuildContext, registry: ModelRegistry, tier: str, system_prompt: str, *, with_models: bool) -> SelectionMiddleware`. This moves `research_agent.agent._decisions_middleware` and `registry_tiers` here unchanged in behaviour, using `TIERS` from `agentkit_core`.
- `resolve.resolve_agent(spec, lib, models, settings, *, model: BaseChatModel | None) -> dict[str, Any]`. It returns kwargs for `build_deep_agent`: `name`, `model` (the instance or a `ModelSpec`), `settings`, `system_prompt` (rendered with `date=datetime.date.today().isoformat()`), `tools`, `subagents` (deepagents `SubAgent` dicts: `name`, `description`, `system_prompt`, `tools`, plus `model` when the subagent sets `model`/`tier` (a `get_model` instance), `skills` when declared, and `response_format` when `response_schema` is set), `middleware` (enabled pool middleware in YAML order, then selection last), and `skills`/`backend`/`permissions` from `skills_mount` when any owner declares skills.
- `output.read_output(result: Mapping[str, Any], path: str | None) -> str`. It returns the file content when `path` is set (the logic of today's `extract_report`); otherwise it returns the last AI message content.
- `load.apply_overrides(spec, overrides: Mapping[str, str]) -> AgentSpec`. Allowed keys are `model`, `tier` and `selection` (where `"off"` means `None`). Any other key is a `SpecErrors`.
- `load.load_agent(path: str | Path, *, settings: Settings, library: Library | None = None, overrides: Mapping[str, str] | None = None, model: BaseChatModel | None = None) -> LoadedAgent`. The library defaults to `Library.for_file(path, CodePools.from_entry_points())`. Order: parse → apply overrides → validate (raise `SpecErrors` if there are any errors; log warnings) → resolve → `build_deep_agent`.
- `@dataclass(frozen=True) LoadedAgent(graph: Any, spec: AgentSpec, model_spec: ModelSpec)`
- `agentkit_config.__init__` exports `load_agent`, `LoadedAgent`, `Library`, `CodePools`, `SpecError`, `SpecErrors`, `read_output`.

- [ ] **Step 1: Write failing tests** (`tmp_path` library, fake tool factories via `CodePools.override`, `scripted` model):
  - `test_end_to_end_yaml_agent_writes_output`: the YAML agent searches, then writes `/report.md`, and `read_output(out, spec.output)` contains the citation.
  - `test_unknown_model_override_fails_before_build`: `overrides={"model": "nope"}` raises `SpecErrors` listing `anthropic`. Monkeypatch `build_deep_agent` to fail if called, and use `Settings(_env_file=None)` with no keys (Review Focus 4).
  - `test_override_rejects_unknown_key`
  - `test_selection_off_override`
  - `test_decisions_requires_openai_key`: `ConfigError` mentioning `OPENAI_API_KEY`.
  - `test_middleware_order`: two pool middleware entries, then selection, appear in that order. `enabled: false` entries are dropped.
  - `test_subagent_tools_replace_parent`: the subagent dict's `tools` holds only its own.
  - `test_prompt_rendered_with_agent_name`
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-config`. Expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make test`. Expect PASS.
- [ ] **Step 5: Commit** `feat(config): resolve and load_agent`.

### Task 8: Convert the research agent

**Files:**
- Create:
  - `libraries/prompts/research/orchestrator.md` and `libraries/prompts/research/researcher.md`, containing byte-for-byte the current `ORCHESTRATOR` / `RESEARCHER` text
  - `libraries/subagents/researcher.yaml` (description exactly `Read-only researcher for one sub-question; returns sourced findings.`, prompt `research/researcher`, tools `[web_search, fetch_url]`)
  - `apps/research_agent/agent.yaml` (`name: research_agent`, `model: fireworks-glm`, `tier: default`, `selection: decisions`, `prompt: research/orchestrator`, `tools: [web_search, fetch_url]`, `subagents: [researcher]`, `output: /report.md`)
- Modify:
  - `apps/research_agent/src/research_agent/agent.py`, reduced to `DEFAULT_AGENT = Path(__file__).parents[2] / "agent.yaml"` and re-exports, or deleted if nothing remains
  - `cli.py` and `eval_cli.py`: replace `--config` with `--agent` (default `DEFAULT_AGENT`), and add `--model`, `--tier` and `--no-selection`. Both use `load_agent(...)` and `read_output`, keep all the current log lines (the resolved provider/model now comes from `LoadedAgent.model_spec`), and keep the exit message `agent finished without writing /report.md`.
  - `apps/research_agent/tests/test_agent.py`: port it to `load_agent` with `CodePools.override(tools={"web_search": fake, "fetch_url": fake})`.
  - `test_snapshot.py`: switch it to the YAML build, recording kwargs at `agentkit_config.load.build_deep_agent`, against the same fixture.
  - `README.md` ("Quickstart", "Test it manually", key table), `Makefile` if needed, `CLAUDE.md` status line
- Delete: `apps/research_agent/config/*.yaml`, `apps/research_agent/src/research_agent/prompts.py`

- [ ] **Step 1: Port the tests first.**
  - `test_yaml_build_matches_python_snapshot`: Task 1's fixture is unchanged, and the YAML build matches it.
  - `test_every_registry_entry_loads_with_model_override`: replaces the "exactly 6 configs" test. For each `ModelRegistry.default().names()`, `load_agent(DEFAULT_AGENT, overrides={"model": n, "selection": "off"}, model=scripted(...), ...)` builds.
  - `test_end_to_end_report_with_citation`: the existing assertions, run via YAML.
  - Both decisions-key tests.
  - `test_cli_from_other_cwd`: `monkeypatch.chdir(tmp_path)`. `cli.run` with the default agent path loads (with `build_deep_agent` monkeypatched and fake pools) without a "file not found" error (Review Focus 5).
- [ ] **Step 2: Run** `make test`. Expect the ported tests to FAIL.
- [ ] **Step 3: Add the YAML and Markdown files, switch the CLIs, then delete the old configs and `prompts.py`.**
- [ ] **Step 4: Run** `make test && make lint`. Expect PASS. Then check by hand: `uv run research --help` shows `--agent` and `--model`.
- [ ] **Step 5: Commit** `refactor(research_agent): build from agent.yaml via load_agent`.

### Task 9: `agentkit validate` CLI in lint

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/cli.py`
- Modify: `Makefile` (append `&& uv run agentkit validate apps/*/agent.yaml apps/*/flows/*.yaml libraries/subagents/*.yaml` to `lint`; the flows glob may match nothing until Task 11, so the CLI must accept zero matches for a glob that the shell leaves literal)
- Test: `packages/agentkit-config/tests/test_cli.py`

**Interfaces:**
- `main(argv: Sequence[str] | None = None) -> int`. It dispatches on each file's `kind`: Agent → `validate_agent`; SubAgent → parse plus validating its refs as a standalone owner; Flow → `validate_flow` once Task 11 exists, and until then an error `"flows not supported yet"`. It prints one line per error/warning (`str(SpecError)`) and returns 1 if any errors exist, otherwise 0. A literal unmatched glob (containing `*`) is skipped. It needs no API keys.

- [ ] **Step 1: Write failing tests:** `test_valid_agent_exit_0`, `test_bad_tool_exit_1_and_prints_path`, `test_warning_only_exit_0`, `test_unmatched_glob_skipped`, `test_runs_without_keys` (with all `*_API_KEY` env vars cleared).
- [ ] **Step 2: Run.** Expect FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `make lint`. Expect PASS, with the warning `researcher ... no response_schema` printed.
- [ ] **Step 5: Commit** `feat(config): agentkit validate CLI wired into make lint`.

### Task 10: Flow spec models

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/spec/flow.py`
- Test: `packages/agentkit-config/tests/test_spec_flow.py`

**Interfaces:**
- `AgentNode(agent: str, input: str | list[str], output: str)`, `FnNode(fn: str)`, `InterruptNode(interrupt: Literal[True])`, and `NodeSpec = AgentNode | FnNode | InterruptNode`. The union is discriminated by which key is present; zero or two keys is an error.
- `Edge(source: str, target: str)` and `Route(source: str, route: str, to: dict[str, str])`
- `FlowSpec(apiVersion, kind: Literal["Flow"], name, description="", state: str, nodes: dict[str, NodeSpec], edges: list[Edge | Route])`
- `parse_flow(path) -> FlowSpec`. A string edge `"A -> B -> C"` expands to `Edge(A,B), Edge(B,C)` (whitespace-tolerant). Fewer than two names is an error. A mapping edge uses keys `from` (aliased to `source`), `route` and `to`. `START`/`END` are kept as literal strings.

- [ ] **Step 1: Write failing tests:** `test_parses_spec_example` (the spec's `research_with_review` YAML), `test_chain_expands`, `test_single_name_chain_error`, `test_node_with_two_kinds_error`, `test_input_list_accepted`.
- [ ] **Step 2: Run.** Expect FAIL. **Step 3: Implement.** **Step 4: Run** `make test`. Expect PASS.
- [ ] **Step 5: Commit** `feat(config): flow spec models`.

### Task 11: Flow validation, compiler and proof flow

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/flow/{__init__,validate,nodes,compile}.py`
- Create: `apps/research_agent/src/research_agent/flow_nodes.py`, `apps/research_agent/flows/research_with_review.yaml` (the spec's example, with `input: [question, critique]` on the research node)
- Modify: `apps/research_agent/pyproject.toml` (entry points `agentkit.schemas`: `research.ReviewState`; `agentkit.nodes`: `research.critique`, `research.needs_rework`), and `cli.py` from Task 9 (Flow dispatch)
- Test: `packages/agentkit-config/tests/test_flow_validate.py`, `packages/agentkit-config/tests/test_flow_compile.py`, `apps/research_agent/tests/test_review_flow.py`

**Interfaces:**
- `flow.validate.validate_flow(spec, lib, models, *, file) -> list[SpecError]` checks:
  - unknown state schema, node fn or router
  - an edge or route target that is not a node, `START` or `END`
  - an agent node whose agent is unknown; a known agent's own `validate_agent` errors are included, prefixed with the agent file path
  - every node reachable from `START`, and `END` reachable from every node
- `flow.nodes`:
  - `agent_node(loaded: LoadedAgent, input: str | list[str], output: str) -> Callable` (async). The message is the single field's value, or `"## {field}\n{value}"` sections joined by a blank line. It returns `{output: read_output(result, loaded.spec.output)}`.
  - `interrupt_node(name: str) -> Callable`. It calls `langgraph.types.interrupt({"node": name})`; the resume value must be a `Mapping`, which is returned as the partial state; anything else raises `TypeError`.
- `flow.compile.load_flow(path, *, settings, library=None, model=None, checkpointer=None) -> CompiledStateGraph`. It validates (raising `SpecErrors`), builds a `StateGraph(state_schema)`, adds nodes (agent nodes via `load_agent(agent_file, settings=settings, library=library, model=model)`), adds edges and `add_conditional_edges(source, router, path_map)`, and compiles. It raises `SpecErrors` when an interrupt node exists and `checkpointer is None`.
- `research_agent.flow_nodes`:
  - `ReviewState(TypedDict, total=False)`: `question: str`, `draft: str`, `critique: str`, `rounds: int`
  - `critique(state) -> dict`: a deterministic check that `draft` contains `"[1]"` and `"Sources"`. It returns `{"critique": "...", "rounds": rounds+1}`.
  - `needs_rework(state) -> Literal["rework","ok"]`: returns `"rework"` when the critique is non-empty and `rounds < 2`.

- [ ] **Step 1: Write failing tests:**
  - `test_unreachable_node_error`
  - `test_unknown_route_target_error`
  - `test_invalid_agent_errors_surface_with_agent_path`
  - `test_interrupt_requires_checkpointer`
  - `test_agent_node_multi_field_message`: the critique text appears in the message the scripted model receives on the second round.
  - `test_review_flow_runs_offline`: scripted model plus fake tool pools plus `InMemorySaver`. The run pauses at `review`, then `Command(resume={})` finishes with `draft` containing `[1]`.
  - `test_interrupt_resume_non_mapping_raises`
- [ ] **Step 2: Run** `make test`. Expect FAIL.
- [ ] **Step 3: Implement, then run `make sync`** for the new entry points.
- [ ] **Step 4: Run** `make test && make lint`. Expect PASS, with `agentkit validate` now checking the flow file.
- [ ] **Step 5: Commit** `feat(config): flow validation, compiler, research_with_review proof flow`.

### Task 12: Re-run T9 through the YAML (live, fireworks-glm only)

Live testing uses **only `fireworks-glm`** (`accounts/fireworks/models/glm-5p3-flash`), per the user's instruction. The other registry entries are covered offline by Task 8's override test. Needs network access, `FIREWORKS_API_KEY`, `OPENAI_API_KEY` (Decisions) and `TAVILY_API_KEY`. No code changes unless a defect turns up.

- [ ] **Step 1:** Run `uv run research "What is the Model Context Protocol?" --model fireworks-glm --out evidence/declarative/glm.md -v 2> evidence/declarative/glm.log`. Pass when the report has at least one `[n]` citation and a Sources section, and the log shows the Decisions selection.
- [ ] **Step 2:** Make a copy of `agent.yaml` with `web_search: {backend: duckduckgo}` and run Step 1's question through it. Pass when the report has at least one citation. This is the one live DuckDuckGo check. If DuckDuckGo rate-limits, record that and don't fail the task.
- [ ] **Step 3:** Run `uv run research-eval --model fireworks-glm --judge anthropic --out evidence/declarative/eval.md`. Pass when no metric is more than 0.10 below the fireworks-glm T9 baseline in `docs/phase0-results.md` (run2: citation_validity 0.96, completeness 0.97, groundedness 0.64, completed 1.0). Record the comparison there.
- [ ] **Step 4: Commit** the evidence summary (not `.env`): `docs: T9 re-run through agent.yaml`.
- [ ] **Step 5: Update the Phase 0b plan** (`docs/superpowers/plans/2026-11-01-agentkit-phase0b-plan.md`): the skills mount becomes one more route inside `memory_backend()`, and regression lanes use `--model` instead of `--config apps/research_agent/config/*.yaml`. Commit `docs(0b): align with declarative loader`.
