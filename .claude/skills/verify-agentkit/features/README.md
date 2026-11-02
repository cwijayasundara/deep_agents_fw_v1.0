# agentkit verification map

This directory is the maintained source for verifying the user-facing behavior of agentkit's CLIs.
Read the index before driving, then use the matching feature file as the recipe. Commands run from
the repo root; `S=.claude/skills/verify-agentkit/scripts`.

## Baseline preconditions

- `make sync` has run on this checkout and `$S/doctor.sh` prints `doctor: OK`.
- `.env` holds `FIREWORKS_API_KEY` and `OPENAI_API_KEY` (names checked by doctor; never print values)
  and does not set `AGENTKIT_TENANT`.
- One `RUN_ID` per verification run (`RUN_ID=$(date +%Y%m%d-%H%M%S)`), tenant `verify-$RUN_ID`,
  stamped with `$S/stamp.sh "$RUN_ID"` for every feature except `agentkit-validate` and the
  ephemeral sub-feature of `research-question`.
- `$S/doctor.sh "$RUN_ID"` reports the tenant healthy before the first live drive.
- Never drive a tenant this run did not stamp.

## Driving conventions

- Live runs use `fireworks-glm` only (agent and judge). Count real turns before starting; an eval
  case is one turn plus judge calls.
- Drive through the helpers so every turn's command, stdout, stderr, exit code and report land in
  `evidence/verify/$RUN_ID/` under a fresh LABEL. Never reuse a LABEL; a retry is a new LABEL.
- Treat commands and questions as literal. Read IDs (thread, trace) from the transcript files, not
  from memory.
- Collect (`$S/collect_evidence.sh "$RUN_ID"`) before cleanup; `$S/cleanup.sh "$RUN_ID"` after
  every attempt, passed or failed.

## Proof and skip reporting

- CLI proof is the command, stdout, stderr and exit code, plus the side effect in a second view:
  the report file's content, `agentkit_usage.csv`, `checkpoints.csv`, `spans.jsonl`.
- `checks.txt` from collect must be all PASS for any persisted feature.
- Record the feature ID, RUN_ID and LABEL with every artifact you cite.
- A step that could not run (rate limit, missing key, Docker down) is reported with the attempted
  command and the unmet precondition, never as verified through another path.
- `scripts/smoke.py` and pytest are offline scaffolding; they never substitute for a live drive.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior,
then exactly four H2 sections in this order: `Sub-features`, `How to get to it (user POV)`,
`Driving it with verify-agentkit scripts` (starts with `Preconditions:`, labeled bullets pairing a
user action with an exact command and observable result), and `Gotchas`. Keep implementation
details out; name only user paths, commands, stable output lines and observable proof.

## Features

- [Research question](./research-question.md): one research turn, ephemeral or persisted, producing a cited report, a usage line and (persisted) a trace and ledger row.
- [Persisted research and resume](./persisted-research-and-resume.md): a second turn on the same thread resumes it, recalls the first turn and is metered and traced on its own.
- [Research eval](./research-eval.md): scored eval on a one-case dataset, JSON and Markdown scores, per-case trace and usage.
- [Tenant isolation](./tenant-isolation.md): stamping, port/key separation, the TenantMismatch pre-check, `make contract` and `make phase0-exit`.
- [agentkit validate](./agentkit-validate.md): offline YAML validation with file:path errors and exit codes.
