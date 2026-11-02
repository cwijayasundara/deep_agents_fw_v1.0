# Research question

An operator asks the research agent one question from the terminal and gets a Markdown report with
inline numbered citations and a `Sources` list of URLs the agent actually fetched, plus a one-line
token `usage:` total. With `--persist` under a stamped tenant the turn is also checkpointed
(encrypted), traced to the tenant's collector and metered into `agentkit_usage`.

## Sub-features

- `rq-ephemeral` runs one turn with no database, prints `thread:` and `usage:`, writes the report.
- `rq-persisted` runs the same turn under tenant `verify-<RUN_ID>` with `--persist`: adds `trace:`,
  one `agentkit_usage` row and checkpoints for the thread.
- `rq-selection` shows the Decisions selection (`selection for thread ...`) on the first model call.
- `rq-progress` streams progress on stderr: model line, tool calls, file write, run time.
- `rq-stack` the shipped agent runs the standard middleware stack: model fallback to
  `fireworks-glm:strong` (`glm-5p3`), retries, a 60 model-call budget, 20 `web_search` and 25 `fetch_url`
  calls for the orchestrator (each researcher delegation has its own 30 calls and 25 tools; the report
  write is never budgeted), and PII redaction/masking of e-mails and card numbers.

## How to get to it (user POV)

- `uv run research "<question>" --model fireworks-glm --out <file>` (ephemeral).
- `scripts/tenant_env.sh <tenant> uv run research "<question>" --tenant <tenant> --persist --model fireworks-glm --out <file>`.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/doctor.sh` is OK. For `rq-persisted`: `$S/stamp.sh "$RUN_ID"` printed `doctor: OK`.
- Budget: one real turn per sub-feature you drive (`rq-selection` and `rq-progress` ride along).

- **Persisted turn.** Ask one question as the tenant. Run `$S/drive_research.sh "$RUN_ID" turn1 "What is the Model Context Protocol and what problem does it solve?"`. `turn1.exit` is `0`; `turn1.stdout` has `thread: <uuid>`, `trace: <32 hex>`, `usage: ...`, `wrote .../turn1.report.md`, and no `resumed thread` line.
- **Progress and selection.** Read `turn1.stderr.log`. It shows `agent ... -> fireworks accounts/fireworks/models/glm-5p3-flash (tier=default, selection=decisions)`, `run: tenant=verify-<RUN_ID> ...`, `selection for thread <uuid>: tier=... tools=...`, at least one `web_search` and `fetch_url` call, and `agent finished in <s>s`. No `selection unavailable` line.
- **Report content.** Open `turn1.report.md`. It answers the question, carries inline `[n]` citations and ends with a `Sources` list of `[n] <url>` lines.
- **Side effects.** Run `$S/collect_evidence.sh "$RUN_ID"`. `checks.txt` is all PASS; `agentkit_usage.csv` has a row whose `thread_id` is turn1's thread, model `accounts/fireworks/models/glm-5p3-flash`, non-zero input/output tokens and non-zero `decisions_input_tokens`; `checkpoints.csv` shows tenant `verify-<RUN_ID>`; `spans-summary.txt` lists turn1's trace id.
- **Stack (rides along, no extra turn).** `turn1.exit` is `0` and the report exists even on a long run: a run that spends its search/fetch budget (offline-tested only; no live run has hit it yet) shows `<- web_search error` / `<- fetch_url error` lines after the 20th search or 25th fetch and still ends with `-> write_file /report.md` and `<- write_file ok`. No `GraphRecursionError` on stderr. The usage row's `model` is `accounts/fireworks/models/glm-5p3-flash` (or `glm-5p3` if Decisions chose `tier=strong`, shown on the `selection for thread` line).
- **Fallback (not a CLI path).** The CLI cannot inject a broken primary model; fallback was proven live with a scratch script (`evidence/phase1/fallback.md`): primary `accounts/fireworks/models/does-not-exist`, selection off, the answer arrived and the ledger row's `model` was `accounts/fireworks/models/does-not-exist,accounts/fireworks/models/glm-5p3`. Rerun that script only when the fallback wiring changes; it is one short turn.
- **Ephemeral turn.** Run `$S/drive_research.sh "$RUN_ID" eph1 "<question>" --ephemeral`. Exit `0`, `thread:` and `usage:` lines, a report, and no `trace:` line (tracing is off without the tenant's collector); no ledger row is written anywhere.

## Gotchas

- DuckDuckGo rate limits show up as `<- web_search error` lines and thin reports; rerun later under a new LABEL rather than changing the backend or the question.
- `agent finished without writing /report.md` (exit 1) is a real failure of this model on this question; record it, do not retry silently.
- Without `FIREWORKS_API_KEY` the shipped agent cannot load for any `--model`: its fallback model is built at load (`ConfigError`, exit 2).
- Fallback is silent: no stderr line says the primary failed, and the `agent ... ->` line still names the primary. Only the usage row's `model` (comma-joined ids) shows it.
- Without `OPENAI_API_KEY` the shipped agent cannot build its selection middleware (`ConfigError`, exit 2). `--no-selection` avoids that but is a different journey; say so if you use it.
- The report's citations are only valid if the URLs appear in the fetched tool output; the eval's `citation_validity` measures that, a single run does not.
