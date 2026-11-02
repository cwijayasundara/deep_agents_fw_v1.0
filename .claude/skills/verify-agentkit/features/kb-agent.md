# Knowledge-base agent

The pilot `apps/kb_agent` answers a question from this repo's own docs, ingested into the tenant's
Postgres (schema `kb`, pgvector), and writes a cited report whose sources are the docs' GitHub URLs. It
reaches the data only through `kb_search` and the read-only `sql_query`, both logged in as the
`kb_reader` role. `agentkit-kb` sets the schema and role up and ingests Markdown; `agentkit tools list`
shows the governed tools.

## Sub-features

- `kb-tools-list` `uv run --no-sync agentkit tools list` prints one `name version side_effects classification owner tenants` line per tool, including `kb_search 1.0.0 read internal platform *` and `sql_query 1.0.0 read confidential platform *`.
- `kb-setup` `agentkit-kb setup --connector kb-docs --reader-password-env KB_READER_PASSWORD` (admin DSN) prints `setup: schema kb and role kb_reader ready (read-only, SELECT on kb)`.
- `kb-ingest` `make kb-ingest KB_ADMIN_DATABASE_URL=...` prints `ingest: <n> chunk(s) from 4 file(s) into kb.kb_docs`.
- `kb-answer` `research --agent apps/kb_agent/agent.yaml` (both KB DSNs = kb_reader) writes a report with `[n]` citations, a `## Sources` list of `https://github.com/.../blob/main/...` URLs, and `kb_search` calls on stderr.
- `kb-gate` the 20-case golden gate (`apps/kb_agent/evals/gates.yaml`), a release check, not a verification drive.

## How to get to it (user POV)

- README "Knowledge-base agent" and `deploy/README.md` "Knowledge base": stamp, `agentkit-kb setup`, `make kb-ingest`, then run `research --agent apps/kb_agent/agent.yaml` with `KB_DATABASE_URL` and `KB_READER_DATABASE_URL` both set to the kb_reader DSN.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/stamp.sh "$RUN_ID"` printed `doctor: OK`; the Postgres port is in the stamp line (`Postgres 127.0.0.1:<p>`).
- `KB_READER_PASSWORD` exported with a throwaway value (never echoed; keep it out of the evidence).
- Budget: ingest embeds about 140 chunks on `fireworks-nomic` (fractions of a cent) plus one agent turn.

- **Tools list (free).** `uv run --no-sync agentkit tools list > "$E/tools-list.txt"`: four lines, `fetch_url`, `kb_search`, `sql_query`, `web_search`, each `1.0.0`.
- **Setup.** `scripts/tenant_env.sh "verify-$RUN_ID" sh -c 'KB_DATABASE_URL="$DATABASE_URL" uv run --no-sync agentkit-kb setup --connector kb-docs --reader-password-env KB_READER_PASSWORD' > "$E/kb-setup.stdout"`: exit 0, the `setup:` line above.
- **Ingest.** `scripts/tenant_env.sh "verify-$RUN_ID" sh -c 'make kb-ingest KB_ADMIN_DATABASE_URL="$DATABASE_URL"' > "$E/kb-ingest.stdout" 2>&1`: exit 0, `ingest: ... into kb.kb_docs`. Make echoes the command with the admin DSN in it: redact it (`sed -i '' -E 's#(postgresql://[^:]+:)[^@]+@#\1***@#g'`) before keeping the file.
- **Answer (one real turn).** With `KB_READER_DATABASE_URL="postgresql://kb_reader:$KB_READER_PASSWORD@127.0.0.1:<p>/agentkit"` and `KB_DATABASE_URL` set to the same value: `$S/drive_research.sh "$RUN_ID" kb-turn "How do I give a tenant its own deployment?" --agent apps/kb_agent/agent.yaml`. Exit 0; stderr shows `kb_search` calls; `kb-turn.report.md` has `[n]` citations and a `## Sources` list of GitHub blob URLs; `collect_evidence.sh` finds its usage row and trace.
- **Privileged login refused.** Not driven by default: pointing `KB_READER_DATABASE_URL` at the admin DSN makes every `sql_query` call return `ERROR: sql_query connector must log in as a read-only role (e.g. kb_reader)`; covered by the pg tests on a throwaway stamp.

## Gotchas

- Both KB variables must be kb_reader DSNs at run time; the admin DSN is only for `setup` and `ingest`, and both must use the same admin login (default privileges).
- `kb_search` opens the vector store on first use, so a wrong DSN shows as `ERROR: kb search failed[...]` in the tool output, not at load. A missing table is `ERROR: knowledge base table kb.kb_docs not found; run agentkit-kb ingest`.
- The kb agent has no Decisions selection, so there is no `selection for thread` line.
- Never run `pytest -m pg packages/agentkit-connectors` against a tenant you want to keep: it resets `kb_reader`'s password.
- The golden gate is 20 turns plus anthropic judging (about 1.5 min at concurrency 6); it is a release check, not a verification drive.
