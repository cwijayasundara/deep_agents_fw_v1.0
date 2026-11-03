# Tool guards

Every tool call of the main agent and its subagents passes a deny-only guard tier before it runs. A
tenant's `AGENTKIT_ALLOWED_SIDE_EFFECTS` (comma list of `read`, `write`, `external`; default
`read,external`) decides which side-effect classes may run. A refused call comes back to the model as
a tool message `Tool call refused by <guard>: <reason>`; the run does not crash, is still metered and
traced, and the agent writes whatever report it can.

## Sub-features

- `tg-allow` with the default policy the research agent calls `web_search` and `fetch_url` and writes a cited report.
- `tg-deny-side-effects` with `AGENTKIT_ALLOWED_SIDE_EFFECTS=read` both tools are refused by `side_effects`; the run exits 0.
- `tg-ledger-on-deny` a denied run still writes its `agentkit_usage` row and trace.
- `tg-tenant-only-env` the variable is honored from `deploy/tenants/<t>.env` only; `scripts/tenant_env.sh` refuses it in the repo `.env`.
- `tg-yaml-cannot-drop` no `agent.yaml` can name, drop or reorder the guard (offline: `agentkit validate`, `test_yaml_cannot_name_the_guard`).

## How to get to it (user POV)

- Set `AGENTKIT_ALLOWED_SIDE_EFFECTS=<classes>` in `deploy/tenants/<t>.env`, then `scripts/tenant_env.sh <t> uv run research "<q>" --tenant <t> --persist`.
- `uv run agentkit tools list` shows each tool's side-effect class.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/doctor.sh "$RUN_ID"` OK for a stamped `verify-$RUN_ID`; fireworks-glm key present. Two real turns.

- **Allowed run.** `$S/drive_research.sh "$RUN_ID" allow "What is the Model Context Protocol and what problem does it solve?"`. Exit `0`; stderr has `orchestrator -> web_search` and `-> fetch_url`; `allow.report.md` has `## Sources`; no `refused by` line.
- **Deny run.** `echo 'AGENTKIT_ALLOWED_SIDE_EFFECTS=read' >> deploy/tenants/verify-$RUN_ID.env` (git-ignored; never commit), then `$S/drive_research.sh "$RUN_ID" deny "<same question>"`. Exit `0`; stderr has `agentkit_middleware.guards | tool call 'web_search' refused by side_effects: ... allowed: ['read']` and the same for `fetch_url`; `deny.report.md` says the tools were blocked and cites no sources.
- **Ledger and trace.** `$S/collect_evidence.sh "$RUN_ID"`; `checks.txt` all PASS, `agentkit_usage.csv` has a row for both threads.

## Gotchas

- Span payloads are masked, so the `Tool call refused by ...` message text is not in `spans.jsonl`; read the guard WARNING lines in `deny.stderr.log` and the report.
- Calls made inside the `researcher` subagent are only covered if the run invokes it; the model decides. Check stderr for `task` calls before claiming subagent coverage (offline: `packages/agentkit-deep/tests/test_guards_integration.py`).
- The deny run depends on the model's choices (it may retry or write a short report); the stable proof is the refusals plus exit 0 plus ledger row.
- Unset the line (or use a fresh tenant) before any allow run on the same tenant.
