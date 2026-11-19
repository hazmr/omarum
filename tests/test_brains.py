from pathlib import Path

from omarum import brains
from omarum.config import Config, load_config


def test_every_provider_is_complete():
    assert {"claude-code", "codex", "gemini-cli", "kimi", "qwen"} <= set(brains.PROVIDERS)
    assert {"anthropic", "openai", "gemini", "groq", "openrouter", "deepseek", "mistral",
            "xai", "together", "ollama", "custom"} <= set(brains.PROVIDERS)
    for pid, p in brains.PROVIDERS.items():
        assert p.id == pid and p.label
        assert p.kind in ("cli", "anthropic", "openai", "gemini")
        assert p.group in ("Subscription", "API", "Local")
        if p.kind == "cli":
            assert p.binary and not p.env_key and p.login_hint
        if p.kind == "openai":
            assert p.id == "custom" or p.base_url.startswith(("https://", "http://localhost"))
        if p.group == "API":
            assert p.env_key.endswith("_API_KEY")
        assert p.default_model == "" or p.default_model in p.models


def test_resolve_defaults_and_old_claude_models():
    p, model = brains.resolve(Config(brain="claude-code", brain_model="sonnet"))
    assert p.id == "claude-code" and model == "sonnet"
    # A model name left over from the Claude subscription means "this provider's default".
    p, model = brains.resolve(Config(brain="gemini", brain_model="sonnet"))
    assert p.id == "gemini" and model == p.default_model
    p, model = brains.resolve(Config(brain="openrouter", brain_model="anthropic/claude-sonnet-5.5"))
    assert model == "anthropic/claude-sonnet-5.5"
    p, model = brains.resolve(Config(brain="codex", brain_model=""))
    assert p.id == "codex" and model == ""


def test_status_cli_and_key():
    have = lambda name: "/usr/bin/" + name if name == "claude" else None  # noqa: E731
    P = brains.PROVIDERS
    assert brains.status(P["claude-code"], {}, which=have) == "ready"
    assert brains.status(P["codex"], {}, which=have) == "not installed"
    assert brains.status(P["openai"], {}, which=have) == "needs key"
    assert brains.status(P["openai"], {"OPENAI_API_KEY": "sk-x"}, which=have) == "ready"
    assert brains.status(P["ollama"], {}, which=have) == "ready"  # local: no key
    assert brains.status(P["custom"], {}, which=have, url="") == "needs endpoint"
    assert brains.status(P["custom"], {}, which=have, url="http://localhost:1234/v1") == "ready"


def test_label():
    assert brains.label(Config(brain="claude-code", brain_model="haiku")) == "Claude Code · haiku"
    assert brains.label(Config(brain="codex", brain_model="")) == "Codex"
    assert brains.label(Config(brain="ollama", brain_model="llama3.2")) == "Ollama · llama3.2"


def test_config_brain_defaults_and_unknown_provider(tmp_path: Path):
    cfg = Config()
    assert cfg.brain == "claude-code" and cfg.brain_url == ""
    f = tmp_path / "config.toml"
    f.write_text('brain = "nope"\nbrain_model = "my-own-model"\n')
    cfg = load_config(f)
    assert cfg.brain == "claude-code"            # unknown provider ignored
    assert cfg.brain_model == "my-own-model"     # any model name is allowed now
    f.write_text('brain = "groq"\n')
    assert load_config(f).brain == "groq"
