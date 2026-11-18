# Omarum Phase 1 (Spike) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Press Super+H → a glowing orb appears top-right → you speak → Rum answers out loud (Whisper → Claude Code on the owner's Pro subscription → Piper), interruptible, so we can judge latency and feel before building the rest.

**Architecture:** Two processes talking over a Unix socket. `omarum daemon` (uv venv, Python 3.12) runs the Pipecat voice pipeline and broadcasts state and audio-level events. `omarum-orb` (system Python 3.14 + PyGObject + GTK4 + gtk4-layer-shell, already installed) draws the orb from those events. They're separate because Pipecat, CUDA and ONNX wheels need Python ≤3.12, while PyGObject is a system package for Python 3.14. Shared pure-stdlib modules (`omarum/ipc.py`, `omarum/theme.py`) are importable from both.

**Tech Stack:** Python 3.12 (uv), pipecat-ai (extras: silero, whisper, piper, local), faster-whisper on CUDA (RTX 3060 6 GB), Claude Code CLI (`claude -p`, subscription login) as the brain, Piper TTS; GTK4 + gtk4-layer-shell 1.3 + PyGObject 3.58 + pycairo (system); Hyprland.

**Spec:** `docs/superpowers/specs/2026-11-18-omarum-design.md` (§5, §5.1, §5.2, §6.2 persona, §6.4 orb, §9 step 1)

## Global Constraints

- App name `omarum`; companion default name `Rum`; config at `~/.config/omarum/config.toml`; socket at `$XDG_RUNTIME_DIR/omarum.sock`.
- **Spike scope only:** no settings app, no memory, no recording, no packaging (spec §9.1). Code is throwaway-quality but structured so phase 2 can keep `ipc.py` and `theme.py`.
- Brain: **Claude Code CLI on the owner's Pro subscription** (no API key, zero extra cost). One persistent process: `claude -p --input-format stream-json --output-format stream-json --include-partial-messages --verbose --tools "" --no-session-persistence --model haiku --system-prompt <persona>`. Never use `--bare` (it skips the subscription login). Personal use only: shared builds must use an API key, Ollama or another provider (spec §3). Measured cold one-shot latency on this machine: Haiku 2.3 s, Sonnet 2.6 s.
- Persona: the spec §6.2 default persona text verbatim, with `{name}` = config `companion_name` and `{user}` = config `user_name` (default: `$USER` capitalized).
- End of turn: VAD silence 600 ms. Session ends after 8 s of silence, on Esc, or on a second toggle (§5.1).
- Orb: Breathing glow style, top-right. User color = theme `accent`, companion color = theme `magenta` (Last Horizon `#c4d8e2`), idle = theme `muted`, error = theme `red` (§6.4).
- Latency target: under 1.5 s from end of user speech to first companion audio (§5.2). Log it on every turn.
- Never read `~/.local/share/superwhisper`.

## Review Focus

1. **`claude` missing, logged out, or Pro usage limit reached** → the daemon must not crash. It emits `{"type":"state","state":"error"}` and the orb pulses red; `omarum status` prints the reason. (Test in Task 4.)
2. **Barge-in**: the user speaks while Rum talks → playback stops within ~200 ms and the user's turn begins. (Interruptions enabled in Task 3; manual check in Task 6.)
3. **Rapid double toggle / toggle while starting** → never two sessions at once. (Test in Task 4.)
4. **Daemon not running** when `omarum toggle` or the orb starts → the CLI prints a clear one-line message and exits 1; the orb retries every 1 s without crashing. (Tests in Tasks 2 and 4; manual in Task 5.)
5. **Missing or unparseable theme `colors.toml`** → the orb falls back to built-in Last Horizon colors. (Test in Task 5.)

---

### Task 1: Project skeleton and config

**Files:**
- Create: `pyproject.toml`, `.python-version` (`3.12`), `.gitignore` (`.venv/`, `__pycache__/`, `.superpowers/`)
- Create: `omarum/__init__.py`, `omarum/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass Config(companion_name: str, user_name: str, brain_model: str, whisper_model: str, whisper_device: str, piper_voice: str, vad_stop_secs: float, idle_timeout_secs: float, orb_position: str)` and `load_config(path: Path | None = None) -> Config`. Defaults: `"Rum"`, `os.environ["USER"].capitalize()`, `"haiku"`, `"large-v3-turbo"`, `"cuda"`, `"en_US-amy-medium"`, `0.6`, `8.0`, `"top-right"`. Missing file → all defaults; unknown keys are ignored.

- [ ] **Step 1:** `git init` in `/home/hazem/Work/omarum`; `uv init --package --name omarum --python 3.12`; `uv add "pipecat-ai[silero,whisper,piper,local]"`; `uv add --dev pytest pytest-asyncio`. Pin the installed pipecat version exactly in `pyproject.toml`.
- [ ] **Step 2: Write failing tests:** `test_defaults_when_file_missing` (`companion_name == "Rum"`, `vad_stop_secs == 0.6`, `idle_timeout_secs == 8.0`); `test_file_overrides` (tmp TOML `companion_name = "Noa"` → `"Noa"`, others default); `test_unknown_keys_ignored`.
- [ ] **Step 3:** `uv run pytest tests/test_config.py -v` → FAIL (import error).
- [ ] **Step 4:** Implement `load_config` with `tomllib`.
- [ ] **Step 5:** Run the tests → PASS.
- [ ] **Step 6:** Commit `feat: project skeleton and config`.

### Task 2: Socket protocol (shared, stdlib only)

**Files:**
- Create: `omarum/ipc.py` (stdlib imports only, so system Python 3.14 can import it)
- Test: `tests/test_ipc.py`

**Interfaces:**
- Produces:
  - `SOCKET_PATH: Path` = `Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarum.sock"`
  - `encode(msg: dict) -> bytes` (one JSON line ending with `\n`); `decode(line: bytes) -> dict` (raises `ValueError` on bad JSON)
  - Events: `{"type":"state","state": "idle"|"listening"|"user_speaking"|"thinking"|"speaking"|"error"|"closed", "reason"?: str}` and `{"type":"level","who":"user"|"companion","value": float 0..1}`
  - Commands: `{"cmd":"toggle"|"start"|"stop"|"status"}`; reply `{"ok": bool, "state": str, "reason"?: str}`
  - `class EventHub` (asyncio): `async serve(path: Path, on_command: Callable[[dict], Awaitable[dict]])`, `broadcast(msg: dict) -> None` (non-blocking; drops slow or closed clients), `async close()`
  - `class DaemonNotRunning(Exception)`; `send_command(cmd: str, path: Path = SOCKET_PATH, timeout: float = 2.0) -> dict` (sync, for the CLI). Raises `DaemonNotRunning` if the socket is missing or refuses the connection.

- [ ] **Step 1: Write failing tests:** `test_encode_decode_roundtrip`; `test_decode_bad_json_raises`; `test_broadcast_reaches_two_clients` (hub on a tmp socket, 2 readers, broadcast `{"type":"state","state":"thinking"}` → both receive it); `test_command_reply` (`on_command` returns `{"ok":True,"state":"idle"}`; `send_command("status")` returns it); `test_send_command_no_daemon_raises`.
- [ ] **Step 2:** `uv run pytest tests/test_ipc.py -v` → FAIL.
- [ ] **Step 3:** Implement with `asyncio.start_unix_server`. A client that sends a command line gets a reply line; every connected client receives broadcasts. Remove a stale socket file before binding.
- [ ] **Step 4:** Run the tests → PASS. Confirm `/usr/bin/python3 -c "import omarum.ipc"` works from the repo root.
- [ ] **Step 5:** Commit `feat: unix socket event/command protocol`.

### Task 3: Voice pipeline with state and level events

**Files:**
- Create: `omarum/persona.py`, `omarum/levels.py`, `omarum/claude_code_llm.py`, `omarum/pipeline.py` (and `omarum/piper_tts.py` only if needed, see below)
- Test: `tests/test_levels.py`, `tests/test_persona.py`, `tests/test_claude_code_llm.py`

**Interfaces:**
- Consumes: `Config` (Task 1); an `emit: Callable[[dict], None]` (the daemon passes `hub.broadcast`).
- Produces:
  - `persona.render(cfg: Config) -> str`: the spec §6.2 text with name and user filled in.
  - `levels.rms_level(pcm16: bytes) -> float`: `min(1.0, sqrt(rms / 32768) * 1.6)`; empty input → `0.0`.
  - `class StateTap(FrameProcessor)`, `__init__(self, emit, who: str)`. Passes every frame through unchanged. For `who="user"` (after transport input): emits `level` for `InputAudioRawFrame` (at most one every 33 ms), `state:user_speaking` on `UserStartedSpeakingFrame`, `state:thinking` on `UserStoppedSpeakingFrame`, and records `time.monotonic()` at the stop. For `who="companion"` (before transport output): `level` for `OutputAudioRawFrame`, `state:speaking` on `TTSStartedFrame`, `state:listening` on `BotStoppedSpeakingFrame`, and logs `latency_ms` at the first audio frame of each turn. The two taps share one `LatencyClock` object.
  - `build_pipeline(cfg: Config, emit) -> tuple[PipelineTask, Callable[[], Awaitable[None]]]` (task, async `stop()`). Chain: `LocalAudioTransport(in+out, SileroVADAnalyzer(stop_secs=cfg.vad_stop_secs))` → `StateTap(user)` → `WhisperSTTService(model=cfg.whisper_model, device=cfg.whisper_device)` → user context aggregator → `ClaudeCodeLLMService(model=cfg.brain_model, system_prompt=persona.render(cfg))` → `PiperTTSService(voice=cfg.piper_voice)` → `StateTap(companion)` → transport output → assistant context aggregator. `PipelineParams(allow_interruptions=True)`. System message = `persona.render(cfg)`.
  - `omarum/claude_code_llm.py`: `class BrainUnavailable(Exception)`; `class ClaudeCodeLLMService(LLMService)`. Starts the persistent `claude` process above on first use (restarts it if it exits). For each user turn, writes one stream-json user message line with the latest user text (the process keeps the conversation history itself). Parses stdout lines: text deltas from partial-message events → `LLMTextFrame`s between `LLMFullResponseStartFrame`/`LLMFullResponseEndFrame`; a `result` event ends the turn; `is_error`/rate-limit results → raise `BrainUnavailable(reason)`. On interruption (`StartInterruptionFrame`), stop forwarding the current turn's remaining text.
  - Use the module paths and argument names of the **pinned** pipecat version. If its Piper service needs an HTTP server, wrap the `piper-tts` package in a minimal `TTSService` subclass in `omarum/piper_tts.py` instead.

- [ ] **Step 1: Write failing tests:** `test_rms_silence_is_zero` (`bytes(3200)` → `0.0`); `test_rms_loud_is_high` (full-scale square wave → `> 0.9`); `test_rms_clamped` (≤ 1.0); `test_rms_empty` → `0.0`; `test_persona_fills_names` (contains `"You are Rum."` and the user name, no `{name}`/`{user}` left); `test_claude_stream_parser` (feed recorded stream-json lines with two text deltas and a `result` → yields the two text chunks then end; a `result` with `is_error: true` → raises `BrainUnavailable`); `test_statetap_emits_user_speaking` (push `UserStartedSpeakingFrame` through `StateTap(emit=events.append, who="user")` using pipecat's test helpers → `{"type":"state","state":"user_speaking"}` in events and the frame passed downstream).
- [ ] **Step 2:** `uv run pytest tests/test_levels.py tests/test_persona.py -v` → FAIL.
- [ ] **Step 3:** Implement `persona.py`, `levels.py`, `pipeline.py`.
- [ ] **Step 4:** Run the tests → PASS.
- [ ] **Step 5: Manual smoke test** (logged-in `claude` on PATH): `uv run python -m omarum.pipeline` runs one session and prints events. Say "hi Rum, how are you?" and expect a spoken reply with `latency_ms` logged. If CUDA fails, set `whisper_device="cpu"`, `whisper_model="small"`, and note it for the report.
- [ ] **Step 6:** Commit `feat: pipecat voice pipeline with state/level taps`.

### Task 4: Daemon, session control and CLI

**Files:**
- Create: `omarum/daemon.py`, `omarum/cli.py`; `[project.scripts] omarum = "omarum.cli:main"`
- Test: `tests/test_daemon.py`

**Interfaces:**
- Consumes: `EventHub`, `send_command`, `DaemonNotRunning` (Task 2); `build_pipeline` (Task 3); `load_config` (Task 1).
- Produces:
  - `class Daemon`, `__init__(self, cfg, hub, pipeline_factory=build_pipeline)`, `async handle(cmd: dict) -> dict`, attribute `state: str`.
    - `toggle`: start a session when `idle`/`closed`/`error`, otherwise stop it. `start`/`stop` are explicit. `status` returns the state plus the last error `reason`.
    - An `asyncio.Lock` makes a start during startup a no-op that returns the current state, so there's never a second session.
    - Staying in `listening` longer than `cfg.idle_timeout_secs` ends the session → `closed`.
    - `shutil.which("claude")` is None → reply `ok=False`, `state="error"`, `reason="claude CLI not found"`, broadcast. `BrainUnavailable` during a session → `error` with its reason (for example the usage-limit message). A factory or runtime exception → `error` with `reason=str(exc)`. The daemon never exits on a session error.
  - CLI `main(argv=None)`: `omarum daemon` | `toggle` | `start` | `stop` | `status`. If the daemon isn't running → print exactly `omarum: daemon not running (start it with: omarum daemon)` to stderr and exit 1.

- [ ] **Step 1: Write failing tests** with a fake pipeline factory that records starts and stops and can emit states: `test_toggle_starts_then_stops`; `test_double_toggle_while_starting_single_session` (two concurrent toggles while the factory awaits → one start); `test_missing_claude_cli_errors_without_crash` (monkeypatch `shutil.which` → None → `ok False`, `state "error"`, `"claude" in reason`; a following `status` still answers); `test_brain_unavailable_sets_error` (fake raises `BrainUnavailable("usage limit")` → `state "error"`, reason contains `"usage limit"`); `test_factory_exception_sets_error`; `test_idle_timeout_closes_session` (`idle_timeout_secs=0.1`, fake stays `listening` → `closed` within 0.3 s); `test_cli_no_daemon_exit_1` (exact message, exit code 1).
- [ ] **Step 2:** `uv run pytest tests/test_daemon.py -v` → FAIL.
- [ ] **Step 3:** Implement `Daemon` and `cli.main`.
- [ ] **Step 4:** `uv run pytest -v` → all PASS.
- [ ] **Step 5: Manual:** `uv run omarum daemon` in one terminal; `uv run omarum toggle` in another → talk → `uv run omarum status`.
- [ ] **Step 6:** Commit `feat: daemon session control and CLI`.

### Task 5: The orb (system Python, GTK4 layer shell)

**Files:**
- Create: `omarum/theme.py` (stdlib only), `orb/omarum_orb.py`, `bin/omarum-orb`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: `SOCKET_PATH`, `decode` and the event shapes (Task 2).
- Produces:
  - `theme.load_palette() -> dict[str, tuple[float, float, float]]` with keys `user`, `companion`, `idle`, `error`, `background`. It reads `colors.toml` in the directory printed by `omarchy theme dir "$(omarchy theme current)"` and maps `accent`, `magenta`, `muted`, `red`, `background`. Any failure (no `omarchy`, missing file, bad TOML, bad hex) falls back to Last Horizon: `#b59790`, `#c4d8e2`, `#584e51`, `#c38b7b`, `#0c0b0c`.
  - `theme.state_color(state: str, palette) -> tuple`: `user_speaking`→user, `speaking`→companion, `error`→error, everything else→idle.
  - `bin/omarum-orb`: `#!/bin/sh` → `exec env LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so /usr/bin/python3 "<repo>/orb/omarum_orb.py"`. The preload is required; without it the window opens as a normal tiled window.
  - Orb window: 160×160, transparent, `Gtk4LayerShell` `Layer.OVERLAY`, anchored top+right with 16 px margins, `KeyboardMode.NONE`, exclusive zone 0. Hidden in `idle`/`closed`; it fades in over 200 ms on any other state. Drawing ports `drawGlow` from `.superpowers/brainstorm/*/content/orb-styles.html` to cairo: 4 layered wobbling blobs, breathing `1 + 0.04·sin(1.3t)`, wobble amplitude `3 + e·22`, colors crossfading over ~0.4 s to `state_color`, level smoothed with `e += (target − e)·0.15` per frame. `thinking` = slow inward pulse (radius × `0.9 + 0.05·sin(3t)`); `error` = red pulse at 1 Hz for 3 s, then hide. 60 fps via `add_tick_callback`. A socket reader thread passes events to the main loop with `GLib.idle_add`; if the socket is unavailable, it retries every 1 s and stays hidden.

- [ ] **Step 1: Write failing tests:** `test_fallback_when_omarchy_missing` (monkeypatch `shutil.which` → None → Last Horizon accent); `test_parses_colors_toml` (tmp `colors.toml` with `accent = "#ff0000"` → `user == (1.0, 0.0, 0.0)`); `test_bad_hex_falls_back`; `test_state_color_mapping` (all 7 states).
- [ ] **Step 2:** `uv run pytest tests/test_theme.py -v` → FAIL.
- [ ] **Step 3:** Implement `theme.py` → PASS; confirm `/usr/bin/python3 -c "import omarum.theme"` works from the repo root.
- [ ] **Step 4:** Implement `orb/omarum_orb.py` and `bin/omarum-orb` (chmod +x).
- [ ] **Step 5: Manual:** run the daemon and `bin/omarum-orb`, then `omarum toggle`. Check that the orb fades in top-right, doesn't steal focus (typing in IntelliJ still works), follows your voice in the accent color and Rum's in soft blue, and fades out after 8 s of silence. Take a `grim` screenshot. Kill the daemon → the orb hides; restart the daemon → it reconnects.
- [ ] **Step 6:** Commit `feat: layer-shell glow orb driven by daemon events`.

### Task 6: Shortcut, spike launcher and the verdict

**Files:**
- Create: `scripts/spike-install.sh`, `docs/spike-report.md`
- Modify: the user's Hyprland bindings. First check how the installed Omarchy loads user bindings (`~/.config/hypr/bindings.*`, `.conf` or `.lua`), then add one Omarum include in that format.

**Interfaces:**
- Consumes: the `omarum` CLI (Task 4) and `bin/omarum-orb` (Task 5).
- Produces: Super+H → `omarum toggle`. `omarum daemon` and `omarum-orb` are started in the background by the script via `uwsm app --` (no systemd unit until phase 5).

- [ ] **Step 1:** Write `spike-install.sh`. It runs `uv tool install --editable .`, checks `hyprctl binds -j` for an existing Super+H (if taken, use Super+Alt+H and print it), writes the binding include, runs `hyprctl reload`, and starts the daemon and orb.
- [ ] **Step 2:** Run it, press the shortcut, and have a 2-minute conversation. Read `latency_ms` from the daemon log: median and worst.
- [ ] **Step 3:** Barge-in check (Review Focus #2): talk over Rum mid-sentence; Rum stops and listens.
- [ ] **Step 4:** Write `docs/spike-report.md`: latency median and worst against the 1.5 s target, GPU or CPU Whisper, the owner's verdict on voice and feel, and the changes to make before phase 2 (for example, trying a cloud voice).
- [ ] **Step 5:** Commit `chore: spike install script and report`.
