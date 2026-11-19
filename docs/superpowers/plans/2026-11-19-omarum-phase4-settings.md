# Omarum Phase 4 (Settings App) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A keyboard-first settings window in Omarchy's style (approved mockup `settings-window-v2.html`) with four tabs: **Companion · Engine · Memory · Conversations**. Every change is saved to `~/.config/omarum/config.toml` and applied live.

**Architecture:** All logic is stdlib-only and unit-tested in the venv: `configio` (validated load and save), `settings_model` (the rows: what each control shows and how ←/→ changes it), `library` (memory facts, journals and conversations on disk). The GTK4 window (`settings/omarum_settings.py`, system Python) only renders the model and maps keys. Saving runs `omarum reload`; the daemon re-reads its config (next conversation uses it) and the orb redraws at once.

**Tech Stack:** Python stdlib (`tomllib`), GTK4 + PyGObject (system Python 3.14), `mpv` for playback, Omarchy theme colors via `omarum.theme`.

**Spec:** `docs/superpowers/specs/2026-11-18-omarum-design.md` §6.3 (settings app), §6.4, §8 (privacy: export/erase), phase 1 deferred minor (config typos crash the daemon).

## Global Constraints

- Look: tabs across the top, flat rows with small group labels, the focused row with an accent bar on the left, `‹ value ›` cyclers, square segmented buttons, square toggles, a footer with key hints. Monospace font. Colors from the current Omarchy theme (`theme.load_palette()` + `colors.toml` foreground/background).
- Keys: ↑/↓ or j/k move, ←/→/h/l or Space change, Enter edit/act, Tab/Shift+Tab or 1–4 switch tabs, `d` forget (Memory) or delete (Conversations), `q`/Esc close.
- No mouse required, but clicks work.
- Every change is saved immediately (no Save button), followed by `omarum reload`.
- Text fields (name, user name, ElevenLabs key) open an inline entry on Enter. The **API key is never shown**: the row reads "set ✓" or "not set", and the key is written to `~/.config/omarum/env` (mode 600), never to `config.toml`.
- `config.toml` keeps keys it doesn't know, and keeps the user's own comment lines at the top.
- Stdlib only for `configio`, `settings_model`, `library` (the system-Python window imports them).
- Commit messages have no co-author trailers.

## Review Focus

1. **A typo or wrong type in config.toml** (`orb_size = "big"`, `voice_primary = "siri"`) → the daemon and orb use defaults for that key and keep running; the settings window shows the default. (Task 1 tests)
2. **Forgetting a fact** → only that line leaves `profile.md`; a backup is kept. (Task 3 test)
3. **Deleting a conversation** → only that folder is removed, after a second `d` press to confirm. (Task 3 test + Task 4 manual)
4. **A config.toml with unknown keys or comments** → preserved after saving. (Task 1 test)
5. **Saving with the daemon not running** → the window keeps working (reload failure ignored). (Task 4 manual)

---

### Task 1: Validated config load and save

**Files:** Create `omarum/configio.py`; Modify `omarum/config.py`; Test `tests/test_configio.py`, `tests/test_config.py`

**Interfaces:**
- `config.CHOICES: dict[str, tuple]` for `brain_model` (`haiku`, `sonnet`, `opus`), `voice_primary` (`elevenlabs`, `zonos3`, `kokoro`, `piper`), `orb_style`, `orb_position`, `orb_colors`, `whisper_device` (`auto`, `cuda`, `cpu`).
- `load_config(path)`: per key, a value of the wrong type (bool vs int vs float vs str; ints accepted for floats) or outside `CHOICES` is ignored with a logged warning and the default used. Never raises on bad content; a TOML syntax error → all defaults plus a warning.
- `configio.save_config(updates: dict, path: Path = CONFIG_PATH) -> None`: rewrites the file with the user's leading `#` comment block preserved, then all existing keys (updated where given), then new keys, in TOML (`str` quoted with escapes, `bool` lowercase, numbers as-is). Writes atomically (temp file + rename) and creates the folder.
- `configio.set_secret(name: str, value: str, path: Path = ENV_PATH) -> None`: replaces or adds `NAME=value` in the env file with mode 600; empty value removes the line. `configio.has_secret(name) -> bool`.

- [ ] **Step 1: Failing tests:** `test_wrong_type_uses_default` (`orb_size = "big"` → 160); `test_unknown_choice_uses_default` (`voice_primary = "siri"` → `elevenlabs`); `test_bad_toml_gives_defaults`; `test_int_accepted_for_float` (`vad_stop_secs = 1` → 1.0); `test_save_preserves_comments_and_unknown_keys`; `test_save_roundtrip_types` (str with a quote, bool, int, float survive `load_config`); `test_set_secret_mode_and_replace` (mode `0o600`, second set replaces, empty removes); `test_has_secret`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(settings): validated config loading and saving`.

### Task 2: Settings model (the rows)

**Files:** Create `omarum/settings_model.py`; Test `tests/test_settings_model.py`

**Interfaces:**
- `@dataclass Row(tab: str, group: str, label: str, key: str | None, kind: str, options: tuple = (), hint: str = "")`, with `kind` ∈ `cycle | seg | toggle | slider | text | secret | info | action`.
- `ROWS: list[Row]`, exactly:
  - **Companion** — *Her*: Name (`companion_name`, text), Your name (`user_name`, text). *Orb*: Style (`orb_style`, seg glow/lines/ring), Position (`orb_position`, cycle), Colors (`orb_colors`, cycle theme/warm/glass/mono), Size (`orb_size`, slider 96–320 step 16). *Conversation*: Ends after silence (`idle_timeout_secs`, slider 4–30 step 2, s), Words needed to interrupt (`interrupt_min_words`, slider 1–6 step 1), Mute mic while Rum talks (`mute_while_speaking`, toggle).
  - **Engine** — *Brain*: Model (`brain_model`, seg haiku/sonnet/opus). *Voice*: Engine (`voice_primary`, seg elevenlabs/zonos3/kokoro), ZONOS3 voice (`zonos3_voice`, cycle Savannah/Willow/Imogen/Wyatt/Rupert/Cillian/Jett), Kokoro voice (`kokoro_voice`, cycle af_heart/af_bella/af_nicole/bf_emma/am_michael/bm_george), ElevenLabs key (`ELEVENLABS_API_KEY`, secret). *Ears*: Whisper device (`whisper_device`, seg auto/cuda/cpu). *Status*: info rows (filled at runtime).
  - **Memory** — *Privacy*: Save recording audio (`record_audio`, toggle), Keep conversations (`retention_days`, cycle 0/7/30/90/365 shown as Forever/7 days/…). Facts and journal are listed by the window from `library` (Task 3).
  - **Conversations** — listed by the window from `library`.
- `display(row, value) -> str` (e.g. `retention_days` 0 → `Forever`, slider with unit, toggle → `on`/`off`, secret → `set ✓`/`not set`).
- `step(row, value, direction: int)`: cycle wraps; seg clamps; slider moves by step within bounds; toggle flips; anything else unchanged.
- `rows_for(tab) -> list[Row]`; `TABS = ("Companion", "Engine", "Memory", "Conversations")`; `FOOTERS: dict[tab, list[str]]`.

- [ ] **Step 1: Failing tests:** `test_every_key_row_is_a_config_field_or_secret`; `test_cycle_wraps`; `test_seg_clamps`; `test_slider_steps_within_bounds` (`orb_size` 320 +1 stays 320; 160 −1 → 144); `test_toggle_flips`; `test_retention_display` (0 → `Forever`, 30 → `30 days`); `test_secret_display`; `test_tabs_in_order`.
- [ ] **Step 2:** Run → FAIL. **Step 3:** Implement. **Step 4:** PASS. **Step 5:** Commit `feat(settings): settings model`.

### Task 3: Library (memory and conversations on disk)

**Files:** Create `omarum/library.py`; Test `tests/test_library.py`

**Interfaces:**
- `facts(store) -> list[str]` (profile lines without `- `); `forget(store, index: int) -> None` (removes that line, backup to `profile.md.bak`).
- `journals(store) -> list[tuple[date, str]]` newest first.
- `@dataclass Talk(dir: Path, day: date, time: str, seconds: int | None, first_line: str, audio: list[Path])`; `talks(store) -> list[Talk]` newest first (duration from `meta.json` `started`/`ended`; `first_line` = first user text, truncated to 60 chars).
- `play_command(talk) -> list[str]`: `["mpv", "--no-video", "--really-quiet", <user audio>, <companion audio>]` played one after another (good enough; true interleaving is later); `[]` if no audio.
- `delete_talk(talk) -> None` (removes the folder; refuses paths outside `store.conversations_dir`).
- `export(store, dest: Path) -> Path`: a `.tar.gz` of the whole data folder.

- [ ] **Step 1: Failing tests:** `test_facts_and_forget_with_backup`; `test_journals_newest_first`; `test_talks_newest_first_with_duration_and_first_line`; `test_play_command`; `test_delete_talk_refuses_outside_store`; `test_export_contains_profile`.
- [ ] **Step 2–4:** RED → implement → GREEN. **Step 5:** Commit `feat(settings): memory and conversation library`.

### Task 4: Reload applies to the daemon; the window itself

**Files:** Modify `omarum/daemon.py` (reload re-reads config), `omarum/cli.py` (`omarum settings`); Create `settings/omarum_settings.py`, `bin/omarum-settings`; Test `tests/test_daemon.py`

**Interfaces:**
- Daemon `reload`: `self.cfg = load_config()` (next session uses it), then broadcasts `{"type":"reload"}`.
- `omarum settings` execs `bin/omarum-settings` (system Python, GTK4, no layer-shell).
- The window: a 900×780 Gtk.Window titled "Omarum", built from `settings_model` and `library`, drawing the mockup's look with GTK widgets + CSS generated from the theme palette; key handling as in Global Constraints; each change → `save_config` / `set_secret` → `send_command("reload")` (errors ignored). The Memory tab lists facts (d = forget, with a footer "press d again to forget") and journals (Enter opens the text in a dialog). The Conversations tab lists talks by day (Enter = play via `play_command`, Space = stop, d d = delete). The Engine tab Status group shows: Claude CLI found, ZONOS3 installed, Kokoro installed, Whisper models present, ElevenLabs key set.

- [ ] **Step 1: Failing test:** `test_reload_rereads_config` (write a tmp config with `brain_model = "sonnet"`, monkeypatch `CONFIG_PATH`, `reload` → `d.cfg.brain_model == "sonnet"`).
- [ ] **Step 2:** RED → implement the daemon change → GREEN.
- [ ] **Step 3:** Implement the window and launcher.
- [ ] **Step 4: Manual:** open it with `omarum settings`, take a `grim` screenshot of each tab; use the keyboard (`wtype`/`ydotool` if present, else note it) to change the orb style → `config.toml` updated and the orb style changes on the next session; forget then restore a fact; close with q.
- [ ] **Step 5:** `uv run pytest -q` → PASS; commit `feat(settings): keyboard-first settings window`; merge; push.
