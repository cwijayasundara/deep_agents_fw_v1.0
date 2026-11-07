export UV_CONSTRAINT = constraints.txt
SYNC = uv sync --python 3.12
.PHONY: kb-ingest tool-schemas sync test lint stamp unstamp contract phase0-exit tenant-required showcase showcase-snapshot
sync:
	$(SYNC)
	@# macOS can mark .pth files hidden; Python >=3.12.11 then skips them and editable installs vanish.
	@if [ "$$(uname)" = Darwin ]; then chflags nohidden .venv/lib/python*/site-packages/*.pth 2>/dev/null || true; fi
test: sync
	uv run pytest
lint: sync
	uv run ruff check . && uv run ruff format --check . && uv run mypy packages/*/src apps/*/src && uv run agentkit validate apps/*/agent.yaml apps/*/flows/*.yaml libraries/subagents/*.yaml
	@if command -v shellcheck >/dev/null 2>&1; then shellcheck -x scripts/*.sh; else echo "lint: shellcheck not installed, skipping scripts/*.sh"; fi

# Per-tenant deployments (deploy/compose.yaml as compose project agentkit-<tenant>).
tenant-required:
	@test -n "$(TENANT)" || { echo "set TENANT, e.g. make $(MAKECMDGOALS) TENANT=tenant-a" >&2; exit 2; }
stamp: tenant-required sync
	scripts/stamp_tenant.sh $(TENANT)
# Stops the tenant and deletes its database volume; keeps deploy/tenants/$(TENANT).env (its AES key).
# The dummy values only satisfy compose's interpolation; `down` acts on the project name.
unstamp: tenant-required
	AGENTKIT_TENANT=$(TENANT) AGENTKIT_PG_PASSWORD=- AGENTKIT_PG_PORT=1 AGENTKIT_OTLP_PORT=1 \
		docker compose -p agentkit-$(TENANT) -f deploy/compose.yaml down -v
contract: tenant-required sync
	scripts/tenant_env.sh $(TENANT) sh -c 'AGENTKIT_TEST_DATABASE_URL="$$DATABASE_URL" exec uv run --no-sync pytest contracts'
phase0-exit: sync
	scripts/phase0_exit.sh

# Regenerate packages/agentkit-tools/tool_schemas.json after a tool schema or version change.
tool-schemas: sync
	uv run --no-sync agentkit tools snapshot

# Ingest the corpus of the pilot kb_agent (this repo's own docs) into the kb-docs connector.
# KB_ADMIN_DATABASE_URL is the admin DSN (the login that ran `agentkit-kb setup`); it is used here only.
kb-ingest: sync
	@test -n "$(KB_ADMIN_DATABASE_URL)" || { echo "set KB_ADMIN_DATABASE_URL to the admin DSN used for agentkit-kb setup" >&2; exit 2; }
	@echo "agentkit-kb ingest --connector kb-docs (admin DSN from KB_ADMIN_DATABASE_URL, not echoed)"
	@KB_DATABASE_URL="$(KB_ADMIN_DATABASE_URL)" uv run --no-sync agentkit-kb ingest --connector kb-docs \
		README.md docs/architecture.md docs/phase*-results.md \
		--source-base https://github.com/cwijayasundara/deep_agents_fw_v1.0/blob/main

# "One chassis, many agents" page. `showcase` serves the live team view (PORT=8766 by default);
# `showcase-snapshot` writes the self-contained customer file (no machine state).
PORT ?= 8766
showcase: sync
	PYTHONPATH=scripts uv run --no-sync python -m showcase --serve --port $(PORT) --open
showcase-snapshot: sync
	PYTHONPATH=scripts uv run --no-sync python -m showcase --write evidence/showcase/showcase.html
