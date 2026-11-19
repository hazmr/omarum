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


class FakeResponse:
    def __init__(self, body):
        import json
        self.body = json.dumps(body).encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _capture(body):
    seen = {}

    def urlopen(req, timeout=None):
        import json
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["json"] = json.loads(req.data)
        return FakeResponse(body)
    return seen, urlopen


def test_complete_openai_payload():
    seen, urlopen = _capture({"choices": [{"message": {"content": "- likes tea"}}]})
    out = brains.complete(Config(brain="groq"), {"GROQ_API_KEY": "g"}, "SYS", "PROMPT", urlopen=urlopen)
    assert out == "- likes tea"
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer g"
    assert seen["json"]["model"] == "llama-3.3-70b-versatile"
    assert seen["json"]["messages"] == [{"role": "system", "content": "SYS"}, {"role": "user", "content": "PROMPT"}]


def test_complete_anthropic_and_gemini_payloads():
    seen, urlopen = _capture({"content": [{"type": "text", "text": "hi"}]})
    assert brains.complete(Config(brain="anthropic"), {"ANTHROPIC_API_KEY": "a"}, "SYS", "P", urlopen=urlopen) == "hi"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "a" and seen["json"]["system"] == "SYS"

    seen, urlopen = _capture({"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]})
    assert brains.complete(Config(brain="gemini"), {"GEMINI_API_KEY": "k"}, "SYS", "P", urlopen=urlopen) == "ab"
    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "k"
    assert "k" not in seen["url"].split("models/")[0]  # the key never goes in the URL


def test_complete_cli_one_shot(tmp_path):
    calls = {}

    class Done:
        returncode, stdout, stderr = 0, "- a fact\n", ""

    def run(cmd, **kw):
        calls["cmd"], calls["kw"] = cmd, kw
        return Done()

    out = brains.complete(Config(brain="qwen"), {}, "SYS", "PROMPT", run_cli=run, which=lambda b: "/x/" + b)
    assert out == "- a fact\n" and calls["cmd"][0] == "qwen"
    assert calls["kw"]["input"].startswith("SYS") and "PROMPT" in calls["kw"]["input"]


def test_complete_errors_are_brain_unavailable():
    import pytest

    def urlopen(req, timeout=None):
        raise OSError("connection refused")

    with pytest.raises(brains.BrainUnavailable, match="Ollama"):
        brains.complete(Config(brain="ollama"), {}, "S", "P", urlopen=urlopen)
    with pytest.raises(brains.BrainUnavailable, match="needs an API key"):
        brains.complete(Config(brain="openai"), {}, "S", "P", urlopen=urlopen)


def test_api_error_reasons_are_readable():
    r = brains.error_reason("Groq", "OpenAILLMService#0 exception: Error code: 401 - {'error': {'message': 'Invalid API Key'}}")
    assert r == "Groq rejected the API key (check it in Omarum settings)"
    r = brains.error_reason("Ollama", "OpenAILLMService#0 exception: Connection error.")
    assert r == "Ollama can't be reached: Connection error."
    r = brains.error_reason("Gemini", "GoogleLLMService#0 exception: 404 model not found")
    assert r.startswith("Gemini failed: ") and "404 model not found" in r


def test_cli_launchers_from_mise_are_skipped():
    """mise's launcher runs an update check first; it hung Claude for minutes (2026-11-19)."""
    from omarum.brains import real_binary

    class R:
        def __init__(self, out, code=0): self.stdout, self.returncode = out, code

    wrapper = "/home/u/.local/share/mise/command-wrappers/bin/claude"
    which = lambda name: wrapper  # noqa: E731
    run = lambda cmd, **kw: R("/home/u/.local/share/mise/installs/claude/2.1/claude\n") if cmd[:2] == ["mise", "which"] else R("", 1)  # noqa: E731
    assert real_binary("claude", which=which, run=run) == "/home/u/.local/share/mise/installs/claude/2.1/claude"
    assert real_binary("claude", which=lambda n: "/usr/bin/claude", run=run) == "/usr/bin/claude"
    assert real_binary("claude", which=lambda n: None, run=run) is None
    failing = lambda cmd, **kw: R("", 1)  # noqa: E731
    assert real_binary("claude", which=which, run=failing) == wrapper  # mise can't say: use the launcher
