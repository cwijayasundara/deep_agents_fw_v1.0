export UV_CONSTRAINT = constraints.txt
SYNC = uv sync --python 3.12
.PHONY: sync test lint
sync:
	$(SYNC)
	@# macOS can mark .pth files hidden; Python >=3.12.11 then skips them and editable installs vanish.
	@if [ "$$(uname)" = Darwin ]; then chflags nohidden .venv/lib/python*/site-packages/*.pth 2>/dev/null || true; fi
test: sync
	uv run pytest
lint: sync
	uv run ruff check . && uv run ruff format --check . && uv run mypy packages/*/src apps/*/src
