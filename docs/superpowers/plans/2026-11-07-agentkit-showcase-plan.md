# agentkit showcase ("One chassis, many agents") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate, from the repo, an interactive single-file page that shows agentkit assembling governed agents
from configured parts. The page has five parts: a recipe matrix, an assembly view, a build-your-own bench, a
replay of a recorded run, and a positioning panel. It runs in presenter and explore modes, can be served
locally, and is written as a snapshot to share.

**Architecture:**
- `scripts/showcase/` is a small stdlib + pyyaml package.
- It reuses `platform_catalog.collect()` for the repo introspection.
- It derives showcase-specific data from that catalog, redacts it, and embeds it as JSON in one self-contained
  HTML template.
- The guard order and the memory routes become exported constants in `agentkit-deep`, so the factory and the
  page read the same source.
- The replay is a committed, trimmed fixture converted from one steered live run.

**Tech Stack:** Python 3.12, pyyaml, vanilla JS/CSS inlined (no CDN), pytest, uv workspace.

**Spec:** `docs/superpowers/specs/2026-11-07-agentkit-showcase-design.md`

## Global Constraints

- Everything except narrative copy and the peer comparison is generated from the repo by introspection; no hand-copied platform facts.
- The snapshot is one self-contained HTML file: inline CSS/JS, no external `src=`/`href=` to http(s) (links to docs in the positioning panel are allowed as `<a>` only).
- The page never runs agents, calls models, or touches Postgres/OTel.
- Denylist (must not appear anywhere in the snapshot, the embedded JSON, the replay fixture or the report text, case-insensitive): `P10`, `P3 `, `thread-to-user binding`, `primitive state plaintext`, `AES key rotation`, `key rotation`, `only env://`, `env:// secrets`, `never pruned`, `tenant filter`, `innermost guard`, `Open items`, `decision debt`.
- Must be named honestly as not built: MCP, HITL approval, sandbox, crons/ambient runs, Slack/channel presence. Skills: "supported; no skills in the library yet".
- Tenant policy shown is `deploy/tenants/example.env` → `AGENTKIT_ALLOWED_SIDE_EFFECTS` (`read,external`), labelled "example tenant"; never read from `os.environ`.
- The snapshot omits machine state: env key names and whether they are set, `.env` keys, DSNs, absolute local paths.
- Run commands on the bench: `uv run agentkit validate <file>` then `uv run research --agent <file>`. A KB-derived agent also lists the prerequisites `KB_DATABASE_URL`/`KB_READER_DATABASE_URL` (kb_reader DSNs) and `uv run agentkit-kb setup|ingest`.
- Live runs: fireworks-glm only, via the `verify-agentkit` skill. The shipped `apps/*/agent.yaml` files are never modified for the demo.
- Conventions: uv workspace, Python 3.12, never commit `.env`.

## Review Focus

1. **A new app directory.** A third `apps/<x>/agent.yaml` appears. The matrix must grow a column without code
   changes, and the "same as platform" logic must still work for 3+ agents. Pinned in Task 2
   (`test_matrix_handles_three_agents`).
2. **Tool refs with params.** `kb_agent` uses `{kb_search: {connector: kb-docs}}` dicts, not plain strings.
   The matrix and assembly must show the tool name and its connector, not a dict repr. Pinned in Task 2
   (`test_tool_ref_dict_renders_name_and_connector`).
3. **A denylisted phrase in report or replay text.** The real research report could contain phrases like "key
   rotation". Redaction applies to the replay and the report too, and the snapshot test scans the final HTML,
   not only the catalog. Pinned in Task 3 (`test_denylist_scrubbed_from_replay_and_report`) and Task 6
   (`test_snapshot_has_no_denylisted_text`).
4. **Missing replay fixture.** On a fresh clone, or before Task 5 runs, the page must still build. The
   replay view then shows "no recorded run". Pinned in Task 6 (`test_builds_without_replay`).
5. **Opening the snapshot offline.** `file://` with no network must render fully. Pinned in Task 6
   (`test_snapshot_is_self_contained`, which allows no external script or stylesheet URLs).

---

### Task 1: Guard order and memory routes as shared constants; commit the catalog on them

**Files:**
- Modify: `packages/agentkit-deep/src/agentkit_deep/factory.py`
- Modify: `packages/agentkit-deep/src/agentkit_deep/memory.py`
- Modify: `packages/agentkit-deep/src/agentkit_deep/__init__.py`
- Modify: `scripts/platform_catalog.py`: delete the hand-written `GUARDS` (line 91) and `MEMORY_TIERS` (line
  60) and read the exported constants instead.
- Add (currently untracked): `scripts/platform_catalog.py`, `scripts/catalog.html`
- Modify: `pyproject.toml`: add `"scripts"` to `testpaths`.
- Test: `packages/agentkit-deep/tests/test_layout_constants.py`, `scripts/tests/test_platform_catalog.py`

**Interfaces:**
- Produces:
  - `agentkit_deep.GUARD_LAYERS: tuple[GuardLayer, ...]`, where `GuardLayer` is a frozen dataclass with
    fields `name: str`, `hook: str` and `checks: str`, and the order is `("TenantGuardMiddleware",
    "GuardMiddleware")`.
  - `agentkit_deep.MEMORY_ROUTES: tuple[MemoryRoute, ...]`, where `MemoryRoute` is a frozen dataclass with
    fields `path`, `backend`, `namespace`, `scope` and `writable: bool`. It is built from `ORG_ROUTE`,
    `USER_ROUTE` and the skills route in `memory.py`.
  - The catalog keys `"fixed_guards"` and `"memory_tiers"` keep their current JSON shape, now built from
    these constants.

- [ ] **Step 1: Write failing tests.**
  - `test_factory_follows_guard_layers`: build an agent through `agentkit_deep.testing` (the fake model
    already used by `test_factory.py`). Assert that the names of the main agent's first
    `len(GUARD_LAYERS)` middleware equal `[g.name for g in GUARD_LAYERS]`, and that every subagent's first
    middleware is named `GUARD_LAYERS[-1].name`.
  - `test_memory_routes_match_backend`: assert `{r.path for r in MEMORY_ROUTES}` equals the route prefixes
    of `memory_backend().routes`.
  - `test_catalog_guards_from_constants`: assert `[g["name"] for g in collect()["middleware"]["fixed_guards"]]
    == [g.name for g in GUARD_LAYERS]`.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-deep/tests/test_layout_constants.py
  scripts/tests/test_platform_catalog.py -v`. Expected: FAIL (ImportError on `GUARD_LAYERS`).
- [ ] **Step 3: Implement.**
  - Define `GuardLayer`/`GUARD_LAYERS` in `factory.py`. `build_deep_agent` keeps building `[tenant_guard,
    guards, *middleware]`. Add an assertion, placed where the list is built, that the class names match
    `GUARD_LAYERS`.
  - Define `MemoryRoute`/`MEMORY_ROUTES` in `memory.py`, and export both from `__init__`.
  - Point the catalog at both, and copy the `hook` and `checks` text from the catalog's current `GUARDS`.
- [ ] **Step 4: Run** the tests from Step 2, then `uv run pytest packages/agentkit-deep -q`. Expected: all
  PASS, and the existing `test_guards_integration.py` is unchanged.
- [ ] **Step 5: Commit.** `feat(deep): export GUARD_LAYERS and MEMORY_ROUTES; catalog reads them`

### Task 2: Showcase data model (matrix + assembly)

**Files:**
- Create: `scripts/showcase/__init__.py`
- Create: `scripts/showcase/model.py`
- Test: `scripts/tests/test_showcase_model.py`

**Interfaces:**
- Consumes: `platform_catalog.collect() -> dict`, `GUARD_LAYERS`, `agentkit_config.stack.STACK_ORDER`.
- Produces:
  - `build_matrix(apps: list[dict]) -> dict` returns `{"agents": [name...], "rows": [{"part": str,
    "cells": {agent: str}, "origin": "platform"|"config"|"coming"}]}`.
    - Rows, in this order: `model`, `fallback`, `prompt`, `tools`, `subagents`, `connectors`, `skills`,
      `middleware`, `guards`, `memory`, `tenant policy`, `evals`, plus `coming` rows for `MCP`, `HITL
      approval`, `sandbox`, `crons/ambient`, `Slack/channel`.
    - The origin is `platform` when every agent's cell is identical and the part is supplied by the
      factory or platform (guards, memory, tenant policy). It is `config` otherwise. `coming` rows have a
      cell value of `"coming (Phase 2)"`.
    - The skills cells read `"supported; none in library yet"` when the library has no skills.
  - `build_assembly(app: dict, catalog: dict) -> dict` returns `{"yaml": str, "lines": [{"n": int, "text":
    str, "part_id": str|None}], "layers": [{"id": str, "kind":
    "guard"|"middleware"|"model"|"tool"|"subagent", "label": str, "source": str (repo-relative path),
    "fixed": bool}]}`.
    - Guard layers come first and are `fixed: true`.
    - Middleware is ordered by `STACK_ORDER`, whatever the YAML order.
    - Every YAML line that names a part has a `part_id` equal to a layer `id`.

- [ ] **Step 1: Write failing tests.**
  - `test_matrix_rows_and_agents`: the agents are `["kb_agent", "research_agent"]`, sorted, and the row
    parts are in the order listed above.
  - `test_guards_row_is_platform` and `test_tools_row_is_config`.
  - `test_skills_row_says_supported`.
  - `test_coming_rows_present`.
  - `test_matrix_handles_three_agents`: pass three synthetic app dicts, and assert there are 3 cells per row
    and the origin logic still holds.
  - `test_tool_ref_dict_renders_name_and_connector`: the `kb_agent` tools cell contains `"kb_search
    (kb-docs)"` and no `{`.
  - `test_assembly_guards_first_and_fixed`.
  - `test_assembly_middleware_in_stack_order`: shuffle the YAML middleware, and assert the layers still
    follow `STACK_ORDER`.
  - `test_every_part_line_links_to_a_layer`: every non-null `part_id` is in the set of layer ids.
- [ ] **Step 2: Run** `uv run pytest scripts/tests/test_showcase_model.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `build_matrix` and `build_assembly` in `scripts/showcase/model.py`, using the app
  dicts produced by `platform_catalog._apps()`. Extend `_apps()` only if a field is missing, such as the raw
  YAML text.
- [ ] **Step 4: Run** the tests from Step 2. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(showcase): recipe matrix and assembly data`

### Task 3: Redaction and the example tenant policy

**Files:**
- Create: `scripts/showcase/redact.py`
- Test: `scripts/tests/test_showcase_redact.py`

**Interfaces:**
- Produces:
  - `DENYLIST: tuple[str, ...]`, holding exactly the phrases in Global Constraints.
  - `scrub(obj: Any) -> Any`, which deep-copies the object.
    - Strings containing a denylisted phrase, case-insensitive, are dropped when they are list items or
      dict values. Inside long text (over 200 characters), only the sentence containing the phrase is
      removed.
    - The keys `env`, `env_keys`, `keys_set`, `dotenv` and `dsn` are dropped, along with any string that
      starts with the absolute repo root.
  - `assert_clean(text: str) -> None` raises `ValueError` naming the first denylisted phrase it finds.
  - `example_tenant_policy() -> list[str]` parses `deploy/tenants/example.env` for
    `AGENTKIT_ALLOWED_SIDE_EFFECTS` and returns `["read", "external"]`.

- [ ] **Step 1: Write failing tests.**
  - `test_scrub_drops_denylisted_items`: one item contains "AES key rotation", and it is gone afterwards.
  - `test_scrub_strips_machine_state`.
  - `test_denylist_scrubbed_from_replay_and_report`: a fake report paragraph mentions "key rotation". After
    `scrub`, `assert_clean` passes and the neighbouring sentences remain.
  - `test_example_tenant_policy == ["read", "external"]`.
  - `test_policy_ignores_os_environ`: use monkeypatch to set `AGENTKIT_ALLOWED_SIDE_EFFECTS=write`, and the
    result is unchanged.
- [ ] **Step 2: Run** `uv run pytest scripts/tests/test_showcase_redact.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** in `redact.py`.
- [ ] **Step 4: Run** the tests from Step 2. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(showcase): denylist scrub and example tenant policy`

### Task 4: Bench data (templates, part options, rule hints, run commands)

**Files:**
- Create: `scripts/showcase/bench.py`
- Test: `scripts/tests/test_showcase_bench.py`

**Interfaces:**
- Consumes: the catalog's tools (with `side_effect`/governance metadata), middleware factories, subagents,
  connectors and skills; `example_tenant_policy()`.
- Produces: `build_bench(catalog: dict) -> dict`, which returns `{"templates": [{"name", "base": app name,
  "spec": dict}], "options": {"tools": [{"name", "side_effect", "params"}], "subagents": [...],
  "connectors": [...], "middleware": [...], "skills": []}, "policy": {"example_tenant": [...], "classes":
  ["read", "write", "external"]}, "rules": [{"id", "message"}], "commands": {"research": [str...], "kb":
  [str...]}}`.
- The rules are data that the JS evaluates. Their ids are `side_effect_not_allowed`,
  `missing_require_output`, `unknown_part`, `kb_tool_without_connector` and `subagent_unknown_tool`.
  Each message ends with "— `agentkit validate` is the authority".
- `commands.research` is `["uv run agentkit validate {file}", "uv run research --agent {file}"]`.
  `commands.kb` is the same plus the prerequisite lines from Global Constraints.

- [ ] **Step 1: Write failing tests.**
  - `test_templates_are_shipped_agents`: there are two templates, built from `apps/*/agent.yaml`.
  - `test_options_cover_registered_tools`: the tool names are equal to the catalog's tool names.
  - `test_policy_is_example_tenant`.
  - `test_rule_ids`.
  - `test_kb_commands_list_prereqs`: the strings `agentkit-kb setup` and `KB_READER_DATABASE_URL` appear.
  - `test_template_spec_passes_real_validate`: write each template spec to `tmp_path`, run
    `agentkit_config.cli.main(["validate", str(path)])`, and get `0`. This proves a cloned template is valid
    as it stands.
- [ ] **Step 2: Run** `uv run pytest scripts/tests/test_showcase_bench.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `build_bench`.
- [ ] **Step 4: Run** the tests from Step 2. Expected: PASS.
- [ ] **Step 5: Commit.** `feat(showcase): bench templates, options, rule hints, commands`

### Task 5: Steered live run → replay fixture

**Files:**
- Create: `evidence/showcase/agent-demo.yaml`. This is a copy of `apps/research_agent/agent.yaml` with
  `tool_call_limit` for `web_search` set to `run_limit: 4`. Everything else is unchanged.
- Create: `scripts/showcase/replay.py`
- Create: `evidence/showcase/replay.json`, `evidence/showcase/report.md`, `evidence/showcase/README.md` (with
  the run id, date, model, question and command).
- Test: `scripts/tests/test_showcase_replay.py`, `scripts/tests/fixtures/spans_min.jsonl` (hand-made, about 8
  spans)

**Interfaces:**
- Produces:
  - `replay_from_spans(spans_path: Path, usage_rows: list[dict]) -> dict`, which returns `{"question": str,
    "model": str, "events": [{"t": float (seconds from start), "kind":
    "model"|"tool"|"subagent"|"guard"|"limit"|"fallback"|"pii"|"output", "label": str, "part_id": str,
    "detail": str (≤ 240 chars)}], "totals": {"tokens": int, "cost_usd": float}}`.
  - `part_id` uses the same id scheme as `build_assembly` layers, so the page can light up the matching
    layer.
  - Each event's `detail` is passed through `scrub` and truncated.
  - CLI: `uv run python -m showcase.replay <spans.jsonl> <usage.json> > evidence/showcase/replay.json`.

- [ ] **Step 1: Write failing tests.**
  - `test_events_ordered_and_typed`.
  - `test_detail_truncated_to_240`.
  - `test_part_ids_match_assembly_scheme`: every event `part_id` is in the `build_assembly` layer ids for
    `research_agent`, or is `"output"`.
  - `test_totals_sum_usage_rows`.
  - `test_secrets_and_dsns_absent`: the fixture has a span attribute holding a `postgresql://` DSN and a
    `sk-` key, and both are absent from the JSON dump.

  The tests use `spans_min.jsonl`. Model it on a real `deploy/otel-out/verify-*/spans.jsonl` line: run one
  verify first if none exists locally, and copy the attribute names rather than inventing them.
- [ ] **Step 2: Run** `uv run pytest scripts/tests/test_showcase_replay.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `replay_from_spans`. Map span names and attributes to kinds. A PII event is a
  tool or model span whose input or output contains the PII middleware's mask or redaction marker. Read the
  marker from `agentkit_middleware`'s PII factory rather than hard-coding it.
- [ ] **Step 4: Run** the tests from Step 2. Expected: PASS.
- [ ] **Step 5: Record the live run with the `verify-agentkit` skill** (fireworks-glm, a throwaway stamped
  tenant).
  - Agent: `--agent evidence/showcase/agent-demo.yaml`.
  - Question: `"Compare today's agentic AI platforms (LangChain/LangSmith, Google ADK, CrewAI, Microsoft Copilot Studio, OpenAI) for an enterprise team. Send follow-ups to demo.buyer@example.com."`
  - Keep the spans and `agentkit_usage` rows from the skill's evidence directory.
- [ ] **Step 6: Convert the run and check it.**
  - Run the CLI from Step 3 to produce `replay.json`.
  - Copy the report to `evidence/showcase/report.md`, passed through `scrub`.
  - Check that `replay.json` has at least one `pii` event and at least one `limit` event:
    `python -c "import json;k={e['kind'] for e in json.load(open('evidence/showcase/replay.json'))['events']};print(k)"`.
  - If either is missing, lower `run_limit` or rephrase so the email reaches a model-visible message,
    re-run, and note it in the README. Do not hand-edit events.
- [ ] **Step 7: Commit.** `feat(showcase): steered research run replay on fireworks-glm`

### Task 6: The page — template, generator, modes

**Files:**
- Create: `scripts/showcase/page.html`. This is the template: one `<script id="data"
  type="application/json">` placeholder `/*__SHOWCASE__*/`, with all CSS and JS inline.
- Create: `scripts/showcase/positioning.yaml`. This is the narrative copy, plus a comparison table with rows
  for LangChain's five components (channel presence, identity, memory, sandboxes, scheduled/ambient) and
  for the peer frameworks (LangSmith Fleet, OpenAI Agent Builder (sunsetting 2026-11-30), Google ADK
  Agent Config, CrewAI, M365 declarative agents, Letta `.af`, Dify, kagent).
  - Each row gives `agentkit: have|partial|coming` and a one-line note, plus a link.
  - The differentiator line reads: "configuration bounded by guardrails the config cannot remove".
- Create: `scripts/showcase/__main__.py`, run as `uv run python -m showcase --serve [--port 8766] [--open]` or
  `--write PATH` (run from `scripts/`, or with `PYTHONPATH=scripts`; a `make showcase` target wraps both).
- Modify: `Makefile`: add `showcase` (serve) and `showcase-snapshot` (writes
  `evidence/showcase/showcase.html`).
- Test: `scripts/tests/test_showcase_page.py`

**Interfaces:**
- Consumes: `build_matrix`, `build_assembly`, `build_bench`, `scrub`, `assert_clean`, and
  `replay.json`/`report.md` (both optional).
- Produces: `render(snapshot: bool) -> str`.
  - It builds `{"matrix", "assemblies": {agent: ...}, "bench", "replay" | None, "report" | None,
    "positioning", "generated_at", "git_sha"}`.
  - It passes the data through `scrub`, embeds it, and runs `assert_clean` on the final HTML.
  - When `snapshot=False` (`--serve`), it may add a team-only `"machine"` block from `collect()`, such as
    the keys that are set.
  - When `snapshot=True`, it never adds that block.

**Page behaviour (the JS):**
- Views, in this order: Matrix, Assembly, Bench, Replay, Positioning.
- Explore mode is the default. A "Start here" strip carries one line per view.
- Presenter mode: the `p` key toggles it, and so does `?present` in the URL.
  - ←/→ step through the views, with one takeaway banner per view, taken from `positioning.yaml`
    `takeaways`.
  - The current matrix or assembly element is highlighted.
- Matrix:
  - Cells are styled by origin: platform, config or coming.
  - Clicking a column opens that agent in Assembly.
  - The "your agent" column fills from the bench's current spec.
- Assembly:
  - Hovering a YAML line highlights its layer, and hovering a layer highlights its lines.
  - Fixed guard layers carry the badge "YAML cannot remove".
  - Each layer shows its repo source path.
- Bench:
  - Pick a template, then toggle the options. The YAML preview updates live, and the rule hints update with
    it.
  - A policy toggle switches between `read` / `+external` / `+write`. The example tenant is preselected and
    labelled.
  - Copy buttons are shown for the run commands.
- Replay:
  - Play, pause and step controls step through the events, and each event lights up its `part_id` layer
    in a mini assembly next to it.
  - Totals for tokens and cost are shown.
  - The report sits in a collapsible panel.
  - With no replay, the view shows "No recorded run in this build".
- Light and dark themes come from `prefers-color-scheme`. The layout works at 390px width without
  horizontal scrolling.

- [ ] **Step 1: Write failing tests.**
  - `test_snapshot_is_self_contained`: no `<script src=` and no `<link rel="stylesheet" href="http`.
  - `test_snapshot_has_no_denylisted_text`: `assert_clean(render(True))`, plus a check for each
    `DENYLIST` phrase.
  - `test_snapshot_has_no_machine_state`: none of `FIREWORKS_API_KEY`, `DATABASE_URL`, `"machine"` or
    `str(ROOT)` appears in `render(True)`.
  - `test_embedded_data_round_trips`: extract the JSON and get the keys listed above.
  - `test_builds_without_replay`: monkeypatch the replay path to a missing file, and `data["replay"] is
    None`.
  - `test_coming_items_named`: the positioning data contains MCP, HITL, sandbox, crons and Slack, each
    marked `coming`.
- [ ] **Step 2: Run** `uv run pytest scripts/tests/test_showcase_page.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `render`, `__main__`, `page.html`, `positioning.yaml` and the Makefile targets.
- [ ] **Step 4: Run** `uv run pytest scripts/tests -q`. Expected: all PASS.
- [ ] **Step 5: Check in a real browser.**
  - Run `make showcase` and open the page. Walk through presenter mode with ←/→ across all five views.
  - In the Bench, toggle a `write` tool with the example tenant selected, and check that the
    `side_effect_not_allowed` hint shows.
  - Play the replay, and check that the PII and limit events light up the `pii` and `tool_call_limit`
    layers.
  - Check the layout at 390px width.
  - Run `make showcase-snapshot` and open the file over `file://` with the network off.
- [ ] **Step 6: Commit.** `feat(showcase): one-chassis page with presenter and explore modes`

### Task 7: Publish and document

**Files:**
- Modify: `README.md`, adding a "Showcase" section: what it is, `make showcase`, `make showcase-snapshot`.
- Modify: `CLAUDE.md`, with one line pointing to the spec, the plan and `make showcase`.

- [ ] **Step 1:** Run `make showcase-snapshot`, then `uv run pytest scripts/tests packages/agentkit-deep -q`.
  Expected: PASS.
- [ ] **Step 2:** Publish `evidence/showcase/showcase.html` with the Artifact tool. It is private, with the
  icon `diagram` and the description "agentkit: one chassis, many agents — configure parts, keep the
  guardrails". Give the user the link, and do not share it on their behalf.
- [ ] **Step 3: Commit.** `docs: showcase usage and pointer`
