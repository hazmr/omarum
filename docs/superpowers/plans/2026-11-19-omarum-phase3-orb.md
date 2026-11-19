# Omarum Phase 3 (The Full Orb) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The orb gets all three approved styles (breathing glow, flowing lines, sound ring), five positions (center with a soft screen dim), adjustable size, color palettes (Omarchy theme, Warm, Glass, Mono), and updates live when the Omarchy theme or the config changes.

**Architecture:** Shape math moves into stdlib-only `omarum/orbshapes.py` (pure functions returning point lists, unit-tested in the venv). The orb (`orb/omarum_orb.py`, system Python + cairo) only strokes and fills those shapes. Placement comes from `omarum/orbplace.py`. A new `reload` command makes the daemon broadcast `{"type": "reload"}`; the orb then re-reads config and palette. An Omarchy `theme-set` hook runs `omarum reload`.

**Tech Stack:** Python 3.12 venv (tests), system Python 3.14 + PyGObject + gtk4-layer-shell + pycairo (orb), Omarchy hooks.

**Spec:** `docs/superpowers/specs/2026-11-18-omarum-design.md` (§6.4 orb, §7 theme integration, §9 step 3); approved mockup `orb-styles.html` (formulas below are ported from it).

## Global Constraints

- Styles: `glow` (default), `lines`, `ring`. Positions: `top-right` (default), `top-center`, `top-left`, `center` (dims the screen to 25% black), `bottom-center`. Margin 16 px.
- Size: `orb_size` in px, default 160, clamped to 96–320.
- Colors: `orb_colors` = `theme` (default, live Omarchy palette made vivid) | `warm` | `glass` | `mono`.
- `omarum/orbshapes.py`, `omarum/orbplace.py`, `omarum/theme.py` and `omarum/config.py` stay **stdlib only** (the orb imports them with system Python).
- The orb never takes keyboard focus and is click-through, including the center dim layer.
- States and their look are unchanged from phase 1 (idle/listening dim, user coral, companion blue, thinking pulse, error pulse).
- Commit messages have no co-author trailers.

## Review Focus

1. **Unknown style/position/colors value in config.toml** (a typo) → the orb falls back to the default, never crashes. (Tasks 1 and 2 tests)
2. **Theme switched while the orb is visible** → colors change within a second, with no restart. (Task 3 test + manual)
3. **Daemon restarts** → the orb reconnects and keeps the user's style. (Task 4 manual)
4. **Center position** → the dim layer never blocks clicks, and disappears when the orb hides. (Task 4 manual)
5. **Huge or tiny `orb_size`** → clamped to 96–320. (Task 2 test)

---

### Task 1: Shapes for the three styles

**Files:** Create `omarum/orbshapes.py`; Test `tests/test_orbshapes.py`

**Interfaces:**
- Produces (all pure; `t` seconds, `e` energy 0..1, `size` px; points are `(x, y)` in a `size×size` box centered at `size/2`):
  - `STYLES = ("glow", "lines", "ring")`; `normalize_style(name: str) -> str` (unknown → `"glow"`).
  - `glow_layers(t, e, size, breathe=1.0) -> list[list[tuple[float, float]]]`: 4 closed outlines, outermost first. Port of the mockup: `rb = base*(0.55+layer*0.12)*breathe*(1+0.04*sin(1.3t)) + e*size*0.05`, `wob = sin(3a+1.7t+layer)*0.5 + sin(5a−2.3t+2·layer)*0.35 + sin(2a+0.8t)*0.4`, `r = rb + wob*(size*0.0125 + e*size*0.0625)*(1+layer*0.3)`, `base = size*0.29`, 91 points.
  - `line_paths(t, e, size) -> list[list[tuple[float, float]]]`: 5 open lines across the circle (radius `size*0.42`); line `k` amplitude `(size*0.04 + e*size*0.44)*(1−|k−2|/5)`, frequency `1.6+0.35k`, phase `t*(1.2+0.25k)+k`, edge envelope `cos(x/R·π/2)²`, x step `size/80`.
  - `ring_points(t, e, size) -> list[tuple[float, float]]`: one closed ring, radius `size*0.34`, `n = sin(8a+4t)*sin(3a−2.2t) + 0.5*sin(13a+6t)`, `r = R + n*(size*0.01 + e*size*0.16)`, 181 points.

- [ ] **Step 1: Failing tests:** `test_normalize_style` (`"lines"`→`"lines"`, `"Sparkles"`→`"glow"`); `test_glow_has_four_closed_layers` (4 lists of 91 points, first point ≈ last); `test_glow_grows_with_energy` (max radius at `e=1` > at `e=0`); `test_glow_fits_box` (all points within `[0, size]` for `e=1`, size 160); `test_lines_are_five_and_flat_when_quiet` (5 paths; at `e=0` max |y−c| < `size*0.05`); `test_ring_radius_stays_near_base` (`e=0` → every radius within `size*0.34 ± size*0.02`).
- [ ] **Step 2:** `uv run pytest tests/test_orbshapes.py -q` → FAIL.
- [ ] **Step 3:** Implement with `math` only.
- [ ] **Step 4:** Run → PASS; `/usr/bin/python3 -c "import omarum.orbshapes"` works.
- [ ] **Step 5:** Commit `feat(orb): shape math for glow, lines and ring styles`.

### Task 2: Placement, size and palettes

**Files:** Create `omarum/orbplace.py`; Modify `omarum/theme.py`, `omarum/config.py`; Test `tests/test_orbplace.py`, `tests/test_theme.py`

**Interfaces:**
- Config: `orb_style: str = "glow"`, `orb_size: int = 160`, `orb_colors: str = "theme"` (`orb_position` already exists).
- `orbplace.POSITIONS`; `normalize_position(name) -> str` (unknown → `"top-right"`); `clamp_size(px) -> int` (96–320, non-numbers → 160); `anchors(position) -> dict` with keys `top, bottom, left, right` (bools) and `margin` (16). Center = no edges anchored. `top-center` = top only. `bottom-center` = bottom only. `dims_screen(position) -> bool` (True only for `center`).
- `theme.PRESETS: dict[str, dict]` for `warm` (user `#ff8a65`, companion `#ffb74d`), `glass` (user `#9ad1ff`, companion `#e0f2ff`), `mono` (user `#e0e0e0`, companion `#ffffff`). Each also has idle `#5a5a5a` and error `#e57373`. `theme.palette_for(colors: str) -> dict`: `"theme"` → `load_palette()`; a preset → that preset; unknown → `load_palette()`.

- [ ] **Step 1: Failing tests:** `test_unknown_position_falls_back`; `test_anchor_table` (each position's edges as above); `test_clamp_size` (`20`→96, `999`→320, `"big"`→160, `200`→200); `test_only_center_dims`; `test_palette_presets` (`palette_for("warm")["user"]` is the warm rgb); `test_unknown_colors_use_theme` (monkeypatch `load_palette` → sentinel).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest -q` → PASS; `/usr/bin/python3 -c "import omarum.orbplace, omarum.theme, omarum.config"` works.
- [ ] **Step 5:** Commit `feat(orb): positions, size and color palettes`.

### Task 3: Live reload (config and Omarchy theme)

**Files:** Modify `omarum/daemon.py`, `omarum/cli.py`, `scripts/spike-install.sh`; Test `tests/test_daemon.py`

**Interfaces:**
- Daemon command `{"cmd": "reload"}` → broadcasts `{"type": "reload"}`, replies with status.
- CLI `omarum reload` (2 s timeout like `status`).
- `spike-install.sh` installs `~/.config/omarchy/hooks/theme-set.d/50-omarum` (executable) containing `#!/bin/sh` and `omarum reload >/dev/null 2>&1 || true`. It must not overwrite other hooks.

- [ ] **Step 1: Failing tests:** `test_reload_broadcasts` (handle reload → hub received `{"type":"reload"}`); `test_cli_reload_command` (fake `send_command` receives `"reload"` with timeout 2.0).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement, plus the hook in the install script.
- [ ] **Step 4:** `uv run pytest -q` → PASS.
- [ ] **Step 5:** Commit `feat(orb): live reload on config or Omarchy theme change`.

### Task 4: The orb uses it all

**Files:** Modify `orb/omarum_orb.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Behavior: reads `load_config()` at start and on every `reload` event: style (`normalize_style`), position (`anchors`), size (`clamp_size`, resizes the window), palette (`palette_for`, colors through `theme.state_color`). Draws with the matching shape function (glow: filled radial-gradient layers + halo as today; lines: stroked paths with the middle line brighter; ring: stroked ring plus a small center dot). For `center`, a second full-screen layer-shell window on `Layer.TOP` with `rgba(0,0,0,0.25*alpha)`, empty input region, fading with the orb. `reload` also re-applies anchors on the live window.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Manual, with the fake event driver:** for each style × {top-right, center}, take a `grim` screenshot while "user speaking" and "speaking" → the shapes match the mockup, and the center dim is visible and click-through (clicking a window behind it works).
- [ ] **Step 3: Manual live checks:** edit `config.toml` (`orb_style = "ring"`) and run `omarum reload` → the orb switches without a restart. Run `omarchy theme set <another theme>` → the colors change, then switch back to the original theme. Kill the daemon → the orb reconnects and keeps the ring style.
- [ ] **Step 4:** `uv run pytest -q` → PASS. Commit `feat(orb): three styles, five positions, palettes, live reload`; push.
