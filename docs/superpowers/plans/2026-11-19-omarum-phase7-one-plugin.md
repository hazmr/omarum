# Omarum Phase 7 (One Plugin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Omarum is one Omarchy plugin. `omarchy plugin add https://github.com/hazmr/omarum` installs everything; `omarchy plugin remove omarum.panel` removes everything that runs (engine, orb, shortcut). Only the user's data (`~/.local/share/omarum`, `~/.config/omarum`) stays on disk.

**Owner decisions (2026-11-19):** install = plugin add only (setup on first load, progress in the panel); the orb is drawn inside the plugin (QML), not a separate GTK program. Owner, verbatim: "I want to make it a whole plugin, like completely one application."

**Architecture:** The repo root carries `manifest.json` (entry `plugin/OmarumPanel.qml`). The plugin:
- **Engine:** a Quickshell `Process` running `uv run --project <repo> python -m omarum.cli daemon`, restarted after a crash (3 s). Before the first run, a setup `Process` runs `uv sync` then `python -m omarum.setup` (JSON progress lines: whisper base.en, kokoro), shown in the panel. No `uv` → the panel says how to get it (`omarchy pkg add uv`).
- **Socket:** a Quickshell `Socket` on `$XDG_RUNTIME_DIR/omarum.sock` for state, audio levels and commands (`tap`, `ptt_down`, `ptt_up`, `status`). Replaces the `omarum watch` / `omarum tap` processes.
- **Orb:** a `PanelWindow` on the overlay layer, click-through, sized and placed from config, drawing the glow / lines / ring styles (ported from `omarum/orbshapes.py` and `orb/omarum_orb.py`) with the orb palette, moved by real levels.
- **Shortcut:** `GlobalShortcut { appid: "omarum"; name: "talk" }` (press = `ptt_down`, release = `ptt_up`) plus a runtime Hyprland bind added with `hyprctl eval 'hl.bind(KEYS, hl.dsp.global("omarum:talk"))'`, re-added on Hyprland `configreloaded`, removed (`hl.unbind`) when the plugin unloads. Nothing written to `~/.config/hypr`.
- **Settings:** the GTK window (`/usr/bin/python3 <repo>/settings/omarum_settings.py`) opened from the panel. Its shortcut editor saves to config; the plugin rebinds when config changes.
- **One-time migration** (`python -m omarum.migrate`, run by setup): disables and removes the phase-5 systemd units, `hypr/omarum.lua` and its `require`, the menu entries, the desktop file, the theme hook, the old `plugins/omarum` link and the `omarum` uv tool.

## Global Constraints

- Plugin id stays `omarum.panel`; the plugin folder is `~/.config/omarchy/plugins/omarum.panel` (a clone from `plugin add`, or a symlink to the repo for development).
- Plugin UI rules: every dynamic text `Text.PlainText`; motion through `Style.duration`; colors from the orb palette (summary JSON) or `Commons.Color`.
- The engine is a child of the shell: unloading the plugin kills it (and its ZONOS3 child via PDEATHSIG).
- Retired: `packaging/systemd/`, `packaging/omarum.desktop`, `packaging/aur/`, `scripts/install.sh`, `scripts/uninstall.sh`, `orb/` (GTK orb), `bin/omarum-orb`, `omarum/shortcuts.py` file writing (shortcut normalization and conflict checks stay).
- No co-author trailers in commits.

## Review Focus

1. Remove the plugin → no omarum process left, no bind left (`hyprctl binds`), no orb layer (`hyprctl layers`).
2. Hyprland config reload → the talk bind comes back.
3. First load on a clean machine without `.venv` → setup runs once, the panel shows progress, then Rum starts.
4. Engine crash → restarted; socket reconnects; orb hides while the engine is down.
5. Hold-to-talk latency from key to mic open stays under ~100 ms (no process spawn on the path).

---

### Task 1: The repo is the plugin
Move `bar/omarum/*` → `plugin/`; root `manifest.json` (entry `plugin/OmarumPanel.qml`, version 0.3.0). `omarchy plugin validate .` passes. Commit.

### Task 2: Setup and migration modules (Python, tested)
`omarum/setup.py` (`python -m omarum.setup`: JSON lines `{"step","done","total","message"}`; downloads base.en and Kokoro when missing; runs migrate). `omarum/migrate.py` (each removal only if it is Omarum's, idempotent; tests on a fake home). `omarum.summary` gains `orb: {style, position, size}` and `talk_shortcut` (raw). Commit.

### Task 3: Engine + socket in the plugin
`plugin/Engine.qml`: setup stage → daemon `Process` with restart; `Socket` client with reconnect, state/levels/reason, `send(cmd)`. Panel uses it (no `omarum watch`/`tap` processes). Commit.

### Task 4: The orb in QML
`plugin/Orb.qml` (PanelWindow overlay, click-through, positions top-right/top-center/top-left/center/bottom-center, size, fade in/out, three styles, levels). Live check with screenshots per state. Commit.

### Task 5: Shortcut owned by the plugin
`plugin/Shortcut.qml`: GlobalShortcut + runtime bind (eval / unbind / re-add on configreloaded); settings' shortcut editor saves config only. Verify press/release reach the daemon. Commit.

### Task 6: Retire the old install path
Delete the retired files; README "Install: omarchy plugin add …"; daemon no longer needs `omarum` on PATH. Commit.

### Task 7: Switch this machine and verify
Run migration, link the plugin, verify every Review Focus item live (process list, binds, layers, crash restart, config reload), then `omarchy plugin remove` → nothing left running; re-add.
