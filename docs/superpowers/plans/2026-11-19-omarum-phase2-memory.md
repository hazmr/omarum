# Omarum Phase 2 (Memory and Recording) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rum remembers the user from day to day. Every conversation is saved locally (both voices plus a hidden transcript). After each conversation Rum updates a plain-text profile of the user, and once a day it writes a journal entry. Every new conversation starts with that memory in Rum's head.

**Architecture:** A `Store` owns the on-disk layout under `~/.local/share/omarum/` (mode 700). Two pipeline taps record the transcript (append-only JSONL, flushed per line) and Pipecat's `AudioBufferProcessor` records both voices. At session start, `context.build_system_prompt()` composes persona + profile + recent journals + date/time into the Claude Code system prompt. After a session ends, the daemon runs the memory passes in a background thread through the same isolated `claude -p` CLI, never blocking the next conversation.

**Tech Stack:** Python 3.12, pipecat-ai 1.16.0 (`AudioBufferProcessor`), `claude` CLI (subscription), `ffmpeg` (libopus) for compression, stdlib `wave`/`json`.

**Spec:** `docs/superpowers/specs/2026-11-18-omarum-design.md` (§6.2 persona and memory, §8 privacy, §9 step 2)

## Global Constraints

- Data root: `~/.local/share/omarum/` (`$XDG_DATA_HOME/omarum`), created with mode **700**; layout exactly as spec §6.2:
  `persona.md`, `memory/profile.md`, `memory/journal/YYYY-MM-DD.md`, `conversations/YYYY-MM-DD/HHMM-<id>/{user.opus, companion.opus, transcript.jsonl, meta.json}`.
- Everything is plain, human-readable text the user can edit. Omarum never loses user edits: it reads files fresh at each use and backs up `profile.md` to `profile.md.bak` before overwriting it.
- Memory passes use the same isolated CLI flags as the brain (`--setting-sources "" --strict-mcp-config --disable-slash-commands --tools "" --no-session-persistence`), model `haiku`, never `--bare`. No other network calls.
- Recording audio is on by default (`record_audio = true`); `retention_days = 0` means keep forever (spec §8).
- Out of scope for this phase (recorded as rulings): searching older conversations and user files during a conversation, window awareness (spec §9 step 6), and the settings UI (phase 4).
- Commit messages have no co-author trailers.

## Review Focus

1. **A memory pass fails** (claude missing, logged out, usage limit, timeout) → profile and journal untouched, daemon keeps running, the next session still works. (Task 5 test)
2. **The model returns junk or an empty profile** → the old profile is kept, never wiped. (Task 5 test)
3. **A session with no speech** (opened and closed straight away) → no conversation folder, no memory pass. (Task 6 test)
4. **The daemon crashes mid-conversation** → the transcript written so far is on disk (one flushed line per utterance). (Task 3 test)
5. **The user hand-edits `profile.md` or `persona.md`** → the next session uses their text as written. (Task 2 test)

---

### Task 1: Store (on-disk layout, privacy, retention)

**Files:**
- Create: `omarum/store.py`
- Modify: `omarum/config.py` (add `record_audio: bool = True`, `retention_days: int = 0`)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `class Store(root: Path = DATA_DIR)` with:
  - `ensure() -> None`: creates root, `memory/journal/`, `conversations/`; chmod 700 on root.
  - properties `persona_path`, `profile_path`, `journal_dir`, `conversations_dir` (Paths).
  - `new_conversation(now: datetime) -> Path`: makes `conversations/YYYY-MM-DD/HHMM-<6 hex>/` and returns it.
  - `journal_path(day: date) -> Path`.
  - `conversations_on(day: date) -> list[Path]`: sorted conversation dirs for that day that contain a non-empty `transcript.jsonl`.
  - `days_without_journal(before: date) -> list[date]`: past days that have conversations but no journal file, oldest first.
  - `prune(retention_days: int, now: datetime) -> int`: deletes day folders older than the retention; `0` deletes nothing; returns the count removed.
  - Reads `DATA_DIR` from `omarum.claude_code_llm` (already defined).

- [ ] **Step 1: Failing tests:** `test_ensure_creates_private_layout` (mode `0o700` on root; the three dirs exist); `test_new_conversation_path` (`now=2026-11-19 21:40` → parent name `2026-11-19`, folder name starts with `2140-`, two calls give distinct folders); `test_days_without_journal` (conversations on 17th and 18th, journal only for 17th, `before=19th` → `[18th]`; a day whose only conversation has an empty transcript is not listed); `test_prune_respects_retention` (folders for 1st and 18th, `retention_days=7`, now=19th → 1st removed, returns 1; `retention_days=0` removes nothing).
- [ ] **Step 2:** `uv run pytest tests/test_store.py -q` → FAIL (import error).
- [ ] **Step 3:** Implement `omarum/store.py` and the two config fields.
- [ ] **Step 4:** `uv run pytest -q` → all PASS.
- [ ] **Step 5:** Commit `feat(memory): on-disk store with private layout and retention`.

### Task 2: Memory in Rum's head (system prompt)

**Files:**
- Create: `omarum/context.py`
- Modify: `omarum/persona.py` (persona comes from `persona.md` when present), `omarum/pipeline.py` (use the built prompt)
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `Store` (Task 1), `persona.DEFAULT_PERSONA`.
- Produces:
  - `persona.load(cfg, store) -> str`: writes `DEFAULT_PERSONA` to `persona.md` if missing, then returns that file's text formatted with `{name}`/`{user}` (unknown `{...}` left as-is, never raising).
  - `context.build_system_prompt(cfg, store, now: datetime) -> str`: sections in this order, each omitted when empty:
    1. the persona;
    2. `## What you know about {user}` + `profile.md` text;
    3. `## Recent days` + the last 3 journal files by date (oldest first, each headed `### YYYY-MM-DD`);
    4. `## Right now` + `It is {Weekday}, {D Month YYYY}, {HH:MM}.`
  - `pipeline.build_pipeline(cfg, emit, store=None)` passes `build_system_prompt(cfg, store or Store(), datetime.now())` as the brain's `system_prompt`.

- [ ] **Step 1: Failing tests:** `test_prompt_includes_profile_and_recent_journals` (profile `- Works on a Spring app`, journals for 15th–18th → the prompt contains the profile line and the 16th–18th headers, not the 15th, in date order); `test_prompt_without_memory_is_just_persona_and_time` (no "What you know" header); `test_hand_edited_persona_is_used` (write `persona.md` = `You are {name}, a pirate.` → the prompt starts `You are Rum, a pirate.`); `test_persona_file_created_on_first_use`; `test_unknown_braces_in_persona_do_not_crash` (`{mood}` stays literally).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `persona.load`, `context.build_system_prompt`, and the pipeline change (keep `persona.render` for tests that use it).
- [ ] **Step 4:** `uv run pytest -q` → all PASS.
- [ ] **Step 5:** Commit `feat(memory): Rum starts each conversation with persona, profile and recent journals`.

### Task 3: Transcript recorder

**Files:**
- Create: `omarum/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Produces:
  - `class TranscriptWriter(path: Path)`: `add(who: str, text: str, at: datetime) -> None` appends `{"at": ISO-8601, "who": "user"|"companion", "text": ...}` and flushes and fsyncs each line; ignores blank text; `lines -> int`.
  - `class TranscriptTap(FrameProcessor)`, `__init__(self, writer: TranscriptWriter, who: str)`. Passes all frames through. `who="user"`: writes each `TranscriptionFrame.text`. `who="companion"`: collects `LLMTextFrame` text between `LLMFullResponseStartFrame` and `LLMFullResponseEndFrame` and writes it once at the end (also on `InterruptionFrame`, so a cut-off reply is still recorded).
  - `read_transcript(path: Path) -> list[dict]` (skips corrupt lines).

- [ ] **Step 1: Failing tests:** `test_writer_appends_and_flushes` (two `add` calls → file has 2 JSON lines readable before the writer is closed); `test_blank_text_ignored`; `test_read_transcript_skips_corrupt_line`; `test_user_tap_records_transcription` (run_test with `TranscriptionFrame("hello", "", "t")` → one user line, frame passed through); `test_companion_tap_joins_streamed_reply` (Start, `LLMTextFrame("Hi ")`, `LLMTextFrame("there.")`, End → one companion line `Hi there.`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `omarum/recorder.py`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(memory): crash-safe transcript recorder`.

### Task 4: Audio recording and session metadata

**Files:**
- Modify: `omarum/recorder.py`, `omarum/pipeline.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: `Store.new_conversation` (Task 1), `TranscriptWriter`/`TranscriptTap` (Task 3).
- Produces:
  - `write_wav(path: Path, pcm16: bytes, sample_rate: int) -> None`.
  - `compress_to_opus(wav: Path, ffmpeg: str | None = shutil.which("ffmpeg")) -> Path`: runs `ffmpeg -y -loglevel error -i X.wav -c:a libopus -b:a 24k X.opus`, deletes the wav on success and returns the opus path; returns the wav path unchanged when ffmpeg is missing or fails.
  - `class Session`: `dir: Path`, `transcript: TranscriptWriter`, `started: datetime`, `finish(user_pcm: bytes, companion_pcm: bytes, sample_rate: int, meta: dict) -> Path | None`. If the transcript has 0 lines, it **deletes the conversation folder** and returns None (Review Focus 3). Otherwise it writes `user.*`/`companion.*` (when `record_audio`) and `meta.json` (`started`, `ended`, `brain_model`, `voices`, `latency_ms` list) and returns the dir.
  - `build_pipeline(cfg, emit, store=None)` now returns `(task, stop, session)`. It adds `TranscriptTap(user)` after STT and `TranscriptTap(companion)` after the LLM, plus `AudioBufferProcessor(num_channels=1)` after `transport.output()`, accumulating its `on_track_audio_data(user_audio, bot_audio, sample_rate, num_channels)` chunks into the session. Recording starts on the pipeline's first `StartFrame`. Use the pinned pipecat 1.16 event names; if they differ, rule and ledger.

- [ ] **Step 1: Failing tests:** `test_write_wav_roundtrip` (`wave.open` reads back rate and frames); `test_compress_falls_back_without_ffmpeg` (`ffmpeg=None` → returns the wav path, file kept); `test_compress_with_ffmpeg` (skip if `shutil.which("ffmpeg")` is None → `.opus` exists and the wav is gone); `test_empty_session_leaves_no_folder`; `test_session_finish_writes_meta_and_audio` (one transcript line, 0.1 s of PCM → `meta.json` has `started`/`ended`, an audio file exists for each side); `test_record_audio_off_writes_no_audio`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Update the daemon's factory contract to the 3-tuple and the `FakeFactory` in `tests/test_daemon.py` (returns a dummy session), keeping all daemon tests green.
- [ ] **Step 4:** `uv run pytest -q` → all PASS.
- [ ] **Step 5:** Commit `feat(memory): record both voices and session metadata`.

### Task 5: Memory passes (profile and journal)

**Files:**
- Create: `omarum/memory.py`
- Test: `tests/test_memory.py`

**Interfaces:**
- Consumes: `Store`, `read_transcript`.
- Produces:
  - `RunClaude = Callable[[str, str], str]` (system, prompt) → text; raises on failure. Default `run_claude(system, prompt, model="haiku", timeout=120)` runs the isolated `claude -p` (flags from Global Constraints) with `cwd=DATA_DIR` and returns stdout; non-zero exit or timeout raises `MemoryPassFailed`.
  - `valid_profile(text: str) -> bool`: non-empty, ≤ 200 lines, every non-blank line starts with `- `.
  - `update_profile(store, transcript: list[dict], cfg, run: RunClaude = run_claude) -> bool`: sends the current profile plus the transcript, asking for the **complete updated profile** as `- fact` lines (add, update, or remove facts; keep the user's own edits; first person about the user; no secrets such as passwords or keys). If the result is valid, backs up to `profile.md.bak` and writes it, returning True; otherwise keeps the file and returns False. Any exception → False, logged.
  - `write_journal(store, day: date, cfg, run: RunClaude = run_claude) -> bool`: summarizes all transcripts of `day` into 3–8 sentences in the companion's voice (what happened, the user's mood, what's unfinished) and writes `journal/YYYY-MM-DD.md`. Never overwrites an existing journal. Failure → False.
  - Prompt texts are module constants `PROFILE_SYSTEM` and `JOURNAL_SYSTEM`.

- [ ] **Step 1: Failing tests** (all with a fake `run`): `test_profile_updated_and_backed_up`; `test_junk_output_keeps_old_profile` (fake returns `"Sure! Here is the profile:"` → unchanged, returns False); `test_empty_output_keeps_old_profile`; `test_runner_failure_keeps_profile` (fake raises `MemoryPassFailed`); `test_prompt_contains_current_profile_and_transcript` (inspect what the fake received); `test_journal_written_once` (second call returns False, file unchanged); `test_journal_failure_writes_nothing`; `test_valid_profile_rules`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement `omarum/memory.py`.
- [ ] **Step 4:** Run → PASS. Then one real smoke run: `uv run python -c` calling `run_claude` with a tiny prompt → returns text (needs the logged-in CLI).
- [ ] **Step 5:** Commit `feat(memory): profile and journal passes through the isolated claude CLI`.

### Task 6: Wire memory into the daemon

**Files:**
- Modify: `omarum/daemon.py`
- Test: `tests/test_daemon.py`

**Interfaces:**
- Consumes: `Session.finish` (Task 4), `update_profile`, `write_journal` (Task 5), `Store.days_without_journal`, `Store.prune`.
- Produces:
  - `Daemon(..., memory_runner: Callable[[Callable[[], None]], None] = default_background)`: after every session end (via `_end` **or** on its own), calls `session.finish(...)`. If it returns a folder, queues one background job: `update_profile(store, transcript, cfg)`. Jobs run one at a time in a single worker thread and never block `handle()`.
  - At daemon start, queue `write_journal` for each of `store.days_without_journal(today)`, then `store.prune(cfg.retention_days, now)`.
  - `status` reply gains `"memory": "idle" | "updating"`.

- [ ] **Step 1: Failing tests** (fake factory returns a fake session whose `finish` returns a dir or None; fake runner runs jobs inline): `test_profile_update_queued_after_session`; `test_empty_session_queues_nothing`; `test_self_ended_session_also_saved`; `test_memory_failure_does_not_break_next_session` (job raises → next `start` still works); `test_journals_for_missing_days_queued_at_start`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest -q` → all PASS.
- [ ] **Step 5: Manual:** `bash scripts/spike-install.sh`. Talk to Rum and mention something memorable ("I'm job hunting this week"), then close. Within about a minute, `~/.local/share/omarum/memory/profile.md` has a matching line and the conversation folder holds `user.opus`, `companion.opus`, `transcript.jsonl` and `meta.json`. Start a new conversation and ask "what do you remember about me?" → Rum mentions it.
- [ ] **Step 6:** Commit `feat(memory): daemon saves conversations and updates memory in the background`; push.
