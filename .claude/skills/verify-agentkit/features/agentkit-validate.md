# agentkit validate

`agentkit validate` checks Agent, SubAgent and Flow YAML files offline, before any key lookup or
network call, and prints every problem as `<file>:<yaml path>: <message>` with the known names for
unknown entries, then a `checked N file(s): E error(s), W warning(s)` total. It exits 1 on any
error, 0 with warnings only.

## Sub-features

- `val-shipped` the shipped agent, flow and subagent files validate with 0 errors (3 known warnings).
- `val-unknown-names` unknown model, tool or prompt are reported with their YAML path and the known names.
- `val-shape` an unknown key or a relative `output` is an error.
- `val-exit` exit 0 without errors, 1 with errors; an unmatched glob is skipped.

## How to get to it (user POV)

- `uv run agentkit validate <files...>`; `make lint` runs it on `apps/*/agent.yaml apps/*/flows/*.yaml libraries/subagents/*.yaml`.

## Driving it with verify-agentkit scripts

Preconditions:

- `make sync` has run. No stamp, network or keys needed; free.
- `EV=evidence/verify/$RUN_ID; mkdir -p "$EV"` (scratch YAML must live inside the repo so `libraries/` resolves).

- **Shipped files.** Run `uv run --no-sync agentkit validate apps/*/agent.yaml apps/*/flows/*.yaml libraries/subagents/*.yaml > "$EV/validate-shipped.out" 2>&1; echo $? > "$EV/validate-shipped.exit"`. Exit `0`; output ends `checked 3 file(s): 0 error(s), 3 warning(s)`; every warning is `no response_schema; completion contract recommended` (the agent's `subagents[0]` appears twice, once through the flow, plus `libraries/subagents/researcher.yaml`).
- **Bad names and shape.** Write `$EV/bad-agent.yaml` with `apiVersion: agentkit/v1`, `kind: Agent`, `name: bad_agent`, `model: no-such-model`, `prompt: research/orchestrator`, `tools: [web_search, nope_tool]`, `output: report.md`. Run `uv run --no-sync agentkit validate "$EV/bad-agent.yaml" > "$EV/validate-bad.out" 2>&1; echo $? > "$EV/validate-bad.exit"`. Exit `1`; lines `...bad-agent.yaml:model: unknown model entry 'no-such-model'; known: anthropic, fireworks-deepseek, fireworks-glm, fireworks-minimax, google_genai, openai`, `...:tools[1]: unknown tool 'nope_tool'; known: fetch_url, web_search`, `...:output: output must be an absolute file path like /report.md`, and `checked 1 file(s): 3 error(s), 0 warning(s)`.
- **Unknown key.** Add `colour: red` to the file and rerun. Exit `1`; the only error is `...bad-agent.yaml:colour: Extra inputs are not permitted` (shape errors stop the name checks).
- **Empty match.** Run `uv run --no-sync agentkit validate "$EV/nothing-*.yaml"`. Exit `0` with `checked 0 file(s): 0 error(s), 0 warning(s)`.

## Gotchas

- A file outside the repo cannot see `libraries/`, so every prompt is unknown (`known: (none)`); keep scratch YAML under `evidence/verify/`.
- Missing API keys are not validation errors; a file that validates can still fail at build with `ConfigError` naming the key.
- Shape errors (unknown keys, wrong `kind`) are reported alone; fix them to see the name errors.
- An unmatched glob exits 0; assert the `checked N file(s)` count, not just the exit code.
