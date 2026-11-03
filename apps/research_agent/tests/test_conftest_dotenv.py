"""The root conftest keeps the real `.env` (API keys) for live and agentkit_eval tests."""

import importlib.util
from pathlib import Path

ROOT_CONFTEST = Path(__file__).resolve().parents[3] / "conftest.py"


def _keeps_dotenv():
    spec = importlib.util.spec_from_file_location("_root_conftest", ROOT_CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._keeps_dotenv


class _Node:
    def __init__(self, *markers: str) -> None:
        self.markers = markers

    def get_closest_marker(self, name: str) -> object | None:
        return name if name in self.markers else None


def test_offline_tests_drop_dotenv() -> None:
    assert _keeps_dotenv()(_Node()) is False


def test_live_and_agentkit_eval_tests_keep_dotenv() -> None:
    keeps = _keeps_dotenv()
    assert keeps(_Node("live")) is True
    # agentkit_eval tests only run under --agentkit-live and need the provider keys in .env.
    assert keeps(_Node("agentkit_eval")) is True
