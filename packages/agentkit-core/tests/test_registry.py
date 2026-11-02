import pytest
from agentkit_core import ConfigError, ModelRegistry, ModelSpec, Provider, Settings, get_model

YAML = """
default_provider: anthropic
models:
  anthropic: {fast: claude-haiku-5-5, default: claude-sonnet-5-5, strong: claude-fable-5-1}
  fireworks-glm:
    provider: fireworks
    fast: accounts/fireworks/models/glm-5p3-flash
    default: accounts/fireworks/models/glm-5p3-flash
    strong: accounts/fireworks/models/glm-5p3-flash
"""


def test_resolve_tiers():
    reg = ModelRegistry.from_yaml_text(YAML)
    assert reg.resolve("anthropic", "strong") == ModelSpec(Provider.ANTHROPIC, "claude-fable-5-1")
    assert reg.resolve("fireworks-glm").provider is Provider.FIREWORKS


def test_unknown_entry_and_tier():
    reg = ModelRegistry.from_yaml_text(YAML)
    with pytest.raises(ConfigError, match="unknown model entry 'nope'"):
        reg.resolve("nope")
    with pytest.raises(ConfigError, match="unknown tier"):
        reg.resolve("anthropic", "huge")


def test_default_registry_covers_all_providers():
    reg = ModelRegistry.default()
    providers = {reg.resolve(n).provider for n in reg.names()}
    assert providers == set(Provider)
    assert {"fireworks-deepseek", "fireworks-glm", "fireworks-minimax"} <= set(reg.names())


def test_missing_key_names_only_selected_provider():
    s = Settings(_env_file=None, openai_api_key=None, anthropic_api_key=None)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        s.require_key(Provider.ANTHROPIC)


def test_get_model_builds_without_network():
    s = Settings(_env_file=None, anthropic_api_key="x", fireworks_api_key="y")
    m = get_model(ModelSpec(Provider.ANTHROPIC, "claude-sonnet-5-5"), s)
    assert m.model == "claude-sonnet-5-5"
    f = get_model(ModelSpec(Provider.FIREWORKS, "accounts/fireworks/models/glm-5p3-flash"), s)
    assert "glm-5p3-flash" in f.model_name


def test_dotenv_wins_over_process_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FIREWORKS_API_KEY=from-dotenv\n")
    monkeypatch.setenv("FIREWORKS_API_KEY", "from-shell")
    s = Settings(_env_file=env)
    assert s.fireworks_api_key.get_secret_value() == "from-dotenv"
    assert "FIREWORKS_API_KEY" in s.keys_present()


def test_find_env_file_walks_up(tmp_path):
    from agentkit_core.settings import find_env_file

    (tmp_path / ".env").write_text("X=1\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == tmp_path / ".env"


@pytest.mark.parametrize(
    ("entry", "strong"),
    [
        ("anthropic", "claude-opus-5-5"),
        ("fireworks-glm", "accounts/fireworks/models/glm-5p3"),
        ("fireworks-minimax", "accounts/fireworks/models/minimax-m3"),
    ],
)
def test_shipped_strong_tier_is_a_bigger_model(entry, strong):
    """Tier switching must change the model: fast/default stay cheap, strong is bigger."""
    r = ModelRegistry.default()
    assert r.resolve(entry, "fast").model_id == r.resolve(entry, "default").model_id
    assert r.resolve(entry, "strong").model_id == strong
