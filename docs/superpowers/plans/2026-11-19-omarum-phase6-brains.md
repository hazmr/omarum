# Omarum Phase 6 (Any Brain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rum thinks with any brain the owner has: any **subscription** they are logged into through its own CLI (Claude Code, Codex/ChatGPT, Gemini CLI, Kimi, Qwen) or any **API** (Anthropic, OpenAI, Gemini, Groq, OpenRouter, DeepSeek, Mistral, xAI, Together, Ollama local, or any OpenAI-compatible URL). Persona and memory stay the same on every brain. Also: no more CUDA out-of-memory when the GPU is full.

**Spec:** `docs/superpowers/specs/2026-11-18-omarum-design.md` §6.1 (swappable engine: "Brain (LLM): Ollama | Claude, Gemini, OpenAI"), §6.2 (same person across brains). Owner, 2026-11-19: "I need any subscription or any API."

**Architecture:** `omarum/brains.py` (stdlib) is the registry: provider id → kind (`cli` | `anthropic` | `openai` | `gemini`), label, env key, default model, model suggestions, base URL, CLI binary. `pipeline.build_pipeline` asks `brains.make_llm(cfg, env, system_prompt, on_error)` for the Pipecat service: Claude Code keeps its persistent stream-json service; other CLIs use a new one-shot-per-turn `CliLLMService` (history in the prompt); APIs use Pipecat's own Anthropic / OpenAI (with `base_url`) / Google services. Memory passes call `brains.complete(cfg, env, system, prompt)` (sync, stdlib HTTP or the CLI) and fall back to the Claude CLI when the chosen brain fails.

## Global Constraints

- Config: `brain` (provider id, default `"claude-code"`), `brain_model` (free text; `""` = provider default; old values `haiku|sonnet|opus` keep working on claude-code), `brain_url` (custom endpoint only). Unknown provider → claude-code with a warning, like other invalid keys.
- Keys live in `~/.config/omarum/env` (mode 600) under each provider's usual name (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `TOGETHER_API_KEY`, `OMARUM_CUSTOM_API_KEY`). Never logged, never in summaries.
- Subscription CLIs run as the owner's own logged-in tools, isolated: an empty working directory under `~/.local/state/omarum/brain`, no tools / read-only / no session persistence where the CLI allows it, stderr captured for the error reason. Personal use (spec §3).
- A brain that isn't ready (CLI missing or logged out, key missing) gives the error state with a reason the panel shows, e.g. "codex is not logged in — run: codex login".
- No co-author trailers in commits.

## Review Focus

1. Switching brains mid-day: the system prompt (persona + profile + journals) reaches every kind of brain.
2. One-shot CLIs get the conversation so far, so Rum remembers what was said two turns ago.
3. A barge-in during a one-shot CLI reply kills that process (no zombie CLIs, no late speech).
4. A missing key or logged-out CLI never crashes the daemon; memory still saves (falls back to Claude CLI or skips cleanly).
5. GPU full: the session still starts on the CPU Whisper model.

---

### Task 1: Whisper never fails on a full GPU

**Files:** Modify `omarum/models.py`, `omarum/pipeline.py`, `omarum/daemon.py`; Test `tests/test_models.py`

- `models.make_stt(cfg, factory)`: tries `pick_whisper(cfg)`; if the factory raises a RuntimeError mentioning "out of memory" (or CUDA), logs it and retries with `(cfg.whisper_cpu_model, "cpu", "int8")`. Daemon runs `gc.collect()` after each session so the previous Whisper model is freed.
- [ ] Failing tests: `test_make_stt_falls_back_to_cpu_on_cuda_oom`, `test_make_stt_reraises_other_errors` → implement → green.
- [ ] Commit `fix(ears): fall back to the CPU Whisper model when the GPU is full`.

### Task 2: Brain registry and config

**Files:** Create `omarum/brains.py`; Modify `omarum/config.py`; Test `tests/test_brains.py`, `tests/test_config.py`

- `PROVIDERS: dict[str, Provider]`; `Provider(id, label, kind, group ("Subscription"|"API"|"Local"), env_key, default_model, models, base_url, binary, login_hint)`.
- `resolve(cfg) -> (Provider, model)`; `status(p, env, which=shutil.which) -> "ready" | "needs key" | "not installed"`; `label(cfg) -> "Codex · gpt-5"`.
- [ ] Failing tests: `test_every_provider_is_complete`, `test_resolve_defaults_and_old_claude_models`, `test_status_cli_and_key`, `test_label`, `test_config_brain_defaults_and_unknown_provider` → implement → green.
- [ ] Commit `feat(brain): provider registry and config`.

### Task 3: Subscription CLIs as brains

**Files:** Create `omarum/cli_llm.py`; Test `tests/test_cli_llm.py`

- `cli_command(provider_id, model, prompt) -> list[str]` for codex (`codex exec --skip-git-repo-check --ephemeral -s read-only --color never [-m M] -`, prompt on stdin), gemini (`gemini --approval-mode plan -o text [-m M] -p ""` + stdin), kimi (`kimi -p PROMPT [-m M]`), qwen (`qwen --approval-mode plan -o text [-m M]` + stdin).
- `build_prompt(system, messages) -> str`: system, then the dialogue so far ("Hazem: … / Rum: …"), then "Rum:".
- `CliLLMService(LLMService)`: per `LLMContextFrame`, spawns the command in the isolated dir, streams stdout lines as text, kills the process on interruption/cleanup; non-zero exit → error with the CLI's last stderr line (+ login hint for auth words).
- [ ] Failing tests: `test_commands_are_isolated`, `test_build_prompt_carries_history`, `test_auth_error_reason`, plus a fake-CLI test (a tiny script) that streams lines and one that exits 1 → implement → green.
- [ ] Commit `feat(brain): Codex, Gemini CLI, Kimi and Qwen subscriptions`.

### Task 4: APIs as brains, wired into the pipeline

**Files:** Modify `omarum/brains.py` (`make_llm`), `omarum/pipeline.py`; Test `tests/test_brains.py`

- `make_llm`: claude-code → `ClaudeCodeLLMService`; cli → `CliLLMService`; anthropic → `AnthropicLLMService`; openai-kind → `OpenAILLMService(base_url=…)` (Ollama needs no key); gemini → `GoogleLLMService`. API brains get the system prompt as the context's first system message.
- Not ready → raise `BrainUnavailable(reason)` before the session starts, so the daemon shows the reason.
- [ ] Failing tests: `test_make_llm_picks_service_per_kind` (monkeypatched constructors), `test_make_llm_missing_key_reason` → implement → green.
- [ ] Commit `feat(brain): any API (Anthropic, OpenAI-compatible, Gemini) in the voice loop`.

### Task 5: Memory passes follow the brain

**Files:** Modify `omarum/memory.py`, `omarum/brains.py` (`complete`); Test `tests/test_memory.py`, `tests/test_brains.py`

- `brains.complete(cfg, env, system, prompt, timeout)`: claude-code → existing `run_claude`; cli → one-shot command; APIs → stdlib `urllib` JSON calls (Anthropic Messages, OpenAI chat completions, Gemini generateContent). Memory uses it, falling back to `run_claude` when it raises and `claude` exists.
- [ ] Failing tests: `test_complete_openai_payload` (fake urlopen), `test_memory_falls_back_to_claude` → implement → green.
- [ ] Commit `feat(memory): profile and journal use the chosen brain`.

### Task 6: Settings, panel, summary

**Files:** Modify `omarum/settings_model.py`, `settings/omarum_settings.py`, `omarum/summary.py`; Test `tests/test_settings_model.py`, `tests/test_summary.py`

- Engine → Brain group: **Provider** (cycle through all providers, display "Codex (subscription) · ready"), **Model** (text; ←/→ cycle the provider's suggestions), **API key** (secret, the provider's env key; hidden for CLIs and Ollama), **Endpoint** (text, custom only).
- Summary `brain` = `brains.label(cfg)`.
- [ ] Failing tests → implement → green. Manual: open settings, switch providers, screenshot.
- [ ] Commit `feat(settings): choose any brain, model and key`.

### Task 7: Live check

- [ ] Reinstall (`scripts/install.sh`), restart services. Claude Code: a real session works (owner's mic not needed: `omarum start`, state reaches listening, no errors). Each other provider: selecting it gives its precise reason in `omarum status` / the panel (not logged in / needs key).
