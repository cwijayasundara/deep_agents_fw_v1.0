export UV_CONSTRAINT = constraints.txt
SYNC = uv sync --python 3.12
.PHONY: sync test lint
sync:
	$(SYNC)
test: sync
	uv run pytest
lint: sync
	uv run ruff check . && uv run ruff format --check . && uv run mypy packages/*/src apps/*/src
