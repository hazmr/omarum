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


class Recorder:
    def __init__(self):
        self.calls = []

    def factory(self, name):
        def make(**kw):
            self.calls.append((name, kw))
            return name
        return make


def _make(cfg, env, rec, which=lambda b: "/usr/bin/" + b):
    factories = {k: rec.factory(k) for k in ("claude-code", "cli", "anthropic", "openai", "gemini")}
    return brains.make_llm(cfg, env, "You are Rum.", on_error=None, factories=factories, which=which)


def test_make_llm_picks_service_per_kind():
    rec = Recorder()
    assert _make(Config(brain="claude-code", brain_model="sonnet"), {}, rec) == "claude-code"
    assert rec.calls[-1][1]["model"] == "sonnet" and rec.calls[-1][1]["system_prompt"] == "You are Rum."
    assert _make(Config(brain="codex", brain_model=""), {}, rec) == "cli"
    assert rec.calls[-1][1]["provider_id"] == "codex"
    assert _make(Config(brain="anthropic"), {"ANTHROPIC_API_KEY": "a"}, rec) == "anthropic"
    assert rec.calls[-1][1] == {"api_key": "a", "model": "claude-haiku-5-5"}
    assert _make(Config(brain="groq"), {"GROQ_API_KEY": "g"}, rec) == "openai"
    assert rec.calls[-1][1]["base_url"] == "https://api.groq.com/openai/v1"
    assert _make(Config(brain="ollama", brain_model="llama3.2"), {}, rec) == "openai"
    assert rec.calls[-1][1]["api_key"] == "ollama"  # local: any non-empty key
    assert _make(Config(brain="custom", brain_url="http://localhost:1234/v1", brain_model="m"), {}, rec) == "openai"
    assert rec.calls[-1][1]["base_url"] == "http://localhost:1234/v1"
    assert _make(Config(brain="gemini"), {"GEMINI_API_KEY": "k"}, rec) == "gemini"
    assert rec.calls[-1][1] == {"api_key": "k", "model": "gemini-2.5-flash"}  # persona comes in the context


def test_make_llm_not_ready_reasons():
    import pytest

    from omarum.claude_code_llm import BrainUnavailable

    rec = Recorder()
    with pytest.raises(BrainUnavailable, match="Gemini needs an API key"):
        _make(Config(brain="gemini"), {}, rec)
    with pytest.raises(BrainUnavailable, match="Codex is not installed"):
        _make(Config(brain="codex"), {}, rec, which=lambda b: None)
    with pytest.raises(BrainUnavailable, match="endpoint"):
        _make(Config(brain="custom"), {}, rec)
    with pytest.raises(BrainUnavailable, match="model"):
        _make(Config(brain="custom", brain_url="http://x/v1", brain_model=""), {}, rec)
    assert rec.calls == []
