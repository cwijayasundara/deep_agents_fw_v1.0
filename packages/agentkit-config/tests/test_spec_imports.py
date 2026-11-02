from __future__ import annotations

import ast
from pathlib import Path

import agentkit_config.spec as spec_pkg

FORBIDDEN = {"langchain", "langchain_core", "langgraph", "deepagents"}


def test_spec_package_has_no_framework_imports() -> None:
    root = Path(spec_pkg.__file__).parent
    offenders = []
    for py in root.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            offenders += [f"{py.name}: {n}" for n in names if n.split(".")[0] in FORBIDDEN]
    assert offenders == []
