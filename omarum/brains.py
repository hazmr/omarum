"""Rum's brain: any subscription (through its own CLI) or any API. Stdlib only.

The registry says what each provider is; `make_llm` (voice loop) and `complete`
(memory passes) turn the configured one into something that answers.
Model suggestions are only suggestions: any model name the provider accepts works.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    kind: str  # cli | anthropic | openai | gemini
    group: str  # Subscription | API | Local
    default_model: str = ""
    models: tuple = ()
    env_key: str = ""
    base_url: str = ""
    binary: str = ""
    login_hint: str = ""
    extra: dict = field(default_factory=dict)


def _cli(pid, label, binary, login, models=(), default=""):
    return Provider(pid, label, "cli", "Subscription", default, models, binary=binary, login_hint=login)


def _api(pid, label, kind, env_key, default, models, base_url=""):
    return Provider(pid, label, kind, "API", default, models, env_key=env_key, base_url=base_url)


PROVIDERS: dict[str, Provider] = {p.id: p for p in [
    # Subscriptions: the user's own logged-in CLI.
    _cli("claude-code", "Claude Code", "claude", "claude  (then /login)", ("haiku", "sonnet", "opus"), "haiku"),
    _cli("codex", "Codex", "codex", "codex login", ("", "gpt-5", "gpt-5-mini")),
    _cli("gemini-cli", "Gemini CLI", "gemini", "gemini  (then sign in with Google)", ("", "gemini-2.5-flash", "gemini-2.5-pro")),
    _cli("kimi", "Kimi", "kimi", "kimi  (then /login)"),
    _cli("qwen", "Qwen Code", "qwen", "qwen  (then /auth)"),
    # APIs: the user's own key.
    _api("anthropic", "Anthropic", "anthropic", "ANTHROPIC_API_KEY", "claude-haiku-5-5",
         ("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")),
    _api("openai", "OpenAI", "openai", "OPENAI_API_KEY", "gpt-5-mini", ("gpt-5-mini", "gpt-5"),
         "https://api.openai.com/v1"),
    _api("gemini", "Gemini", "gemini", "GEMINI_API_KEY", "gemini-2.5-flash",
         ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite")),
    _api("groq", "Groq", "openai", "GROQ_API_KEY", "llama-3.3-70b-versatile",
         ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"), "https://api.groq.com/openai/v1"),
    _api("openrouter", "OpenRouter", "openai", "OPENROUTER_API_KEY", "openrouter/auto",
         ("openrouter/auto",), "https://openrouter.ai/api/v1"),
    _api("deepseek", "DeepSeek", "openai", "DEEPSEEK_API_KEY", "deepseek-chat",
         ("deepseek-chat",), "https://api.deepseek.com/v1"),
    _api("mistral", "Mistral", "openai", "MISTRAL_API_KEY", "mistral-small-latest",
         ("mistral-small-latest", "mistral-large-latest"), "https://api.mistral.ai/v1"),
    _api("xai", "xAI", "openai", "XAI_API_KEY", "grok-3-mini", ("grok-3-mini", "grok-3"), "https://api.x.ai/v1"),
    _api("together", "Together", "openai", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo",
         ("meta-llama/Llama-3.3-70B-Instruct-Turbo",), "https://api.together.xyz/v1"),
    # Local / anything else that speaks the OpenAI API.
    Provider("ollama", "Ollama", "openai", "Local", "llama3.2", ("llama3.2", "qwen2.5", "gemma3"),
             base_url="http://localhost:11434/v1"),
    Provider("custom", "Custom (OpenAI-compatible)", "openai", "Local", "", (), env_key="OMARUM_CUSTOM_API_KEY"),
]}

DEFAULT = "claude-code"
CLAUDE_SUBSCRIPTION_MODELS = ("haiku", "sonnet", "opus")


def resolve(cfg) -> tuple[Provider, str]:
    """(provider, model to ask for; "" = the CLI's own default)."""
    p = PROVIDERS.get(cfg.brain, PROVIDERS[DEFAULT])
    model = (cfg.brain_model or "").strip()
    if p.id != "claude-code" and model in CLAUDE_SUBSCRIPTION_MODELS:
        model = ""  # left over from the Claude subscription
    return p, model or p.default_model


def status(p: Provider, env: dict, which=shutil.which, url: str = "") -> str:
    """ready | not installed | needs key | needs endpoint."""
    if p.kind == "cli":
        return "ready" if which(p.binary) else "not installed"
    if p.id == "custom":
        return "ready" if url.strip() else "needs endpoint"
    if p.group == "API" and not env.get(p.env_key):
        return "needs key"
    return "ready"


def label(cfg) -> str:
    p, model = resolve(cfg)
    return f"{p.label} · {model}" if model else p.label
