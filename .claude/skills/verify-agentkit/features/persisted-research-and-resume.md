# Persisted research and resume

A persisted research thread survives the process: a second `research` call with `--thread <id>`
resumes the same thread, prints where it resumed, sees the first turn's conversation, reuses the
stored Decisions selection, and is metered as its own `agentkit_usage` row on the same thread.
User memory under `/memories/` persists across threads for the same user.

## Sub-features

- `resume-thread` resumes an existing thread and prints `resumed thread <id> at step <n>`.
- `resume-context` the second turn's answer builds on the first turn (follow-up question resolves).
- `resume-selection` the second turn makes no new Decisions call (`decisions_input_tokens` 0 on its row).
- `resume-ledger` each turn adds one `agentkit_usage` row on the same `thread_id`.
- `resume-guard` `--thread` without `--persist` is refused (exit 2).

## How to get to it (user POV)

- `scripts/tenant_env.sh <tenant> uv run research "<q1>" --tenant <tenant> --persist` then
  `scripts/tenant_env.sh <tenant> uv run research "<q2>" --tenant <tenant> --persist --thread <id>`.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/stamp.sh "$RUN_ID"` printed `doctor: OK`.
- Budget: two real turns.

- **First turn.** Run `$S/drive_research.sh "$RUN_ID" turn1 "What is the Model Context Protocol and what problem does it solve?"`. Exit `0`, `thread: <uuid>`, no `resumed thread` line.
- **Resume.** Run `$S/drive_research.sh "$RUN_ID" turn2 "How does it compare to plain function calling?" --thread "$(sed -n 's/^thread: //p' "evidence/verify/$RUN_ID/turn1.stdout")"`. Exit `0`; `turn2.stdout` has `thread: <same uuid>` then `resumed thread <same uuid> at step <n>` with `n` > 0, then `trace:` (a different trace id) and `usage:`.
- **Context carried.** Open `turn2.report.md`. "it" is resolved as the Model Context Protocol without being restated in the question.
- **Ledger and selection.** Run `$S/collect_evidence.sh "$RUN_ID"`. `agentkit_usage.csv` holds two rows with the same `thread_id`; turn2's row has `decisions_input_tokens` `0`; `checkpoints.csv` shows one thread with `max_step` above turn1's `n`; both trace ids are in `spans-summary.txt`; `checks.txt` all PASS.
- **Guard (free).** Run `uv run --no-sync research "x" --thread 00000000-0000-0000-0000-000000000000`. Exit `2` and stderr `--thread resumes a persisted thread; add --persist (needs DATABASE_URL)`.

## Gotchas

- Resuming with a thread id that does not exist silently starts a new thread under that id (no `resumed` line). Assert the line, not just exit 0.
- Turns on one thread are serialized by an advisory lock; a second concurrent turn on the same thread waits, it does not fail.
- Threads are encrypted with the tenant's AES key; after `cleanup.sh` deleted the env file the thread is unrecoverable by design. Resume within one RUN_ID.
- There is no thread-to-user binding yet (open item P10): another user id can resume a thread. Do not report that as a pass of user isolation.
