# Settings redesign: Superwhisper's look, fewer options, every model downloadable

Date: 2026-11-20 · Status: waiting for Hazem's approval

## Why

Hazem doesn't like how Rum's settings window looks or feels, and wants it "exactly like"
Superwhisper's settings window (sizes, fonts, structure) and "simple as possible". Separately,
Rum mishears him ("Rum" → "ROM") because she always runs the small Whisper Base model on the CPU:
Large v3 Turbo is already downloaded (1.6 GB) but the NVIDIA libraries it needs for the GPU are
missing, so Rum silently falls back. Superwhisper shows each model, its size and its download
state, and lets you download it from the window; Rum has no such thing (models come only from the
one-time setup). Hazem asked for that same download handling for **every** model.

## Goals

1. The settings window looks like Superwhisper's: same type size, row height, column positions,
   section titles, switch, slider, segmented buttons and footer (measured below).
2. As few rows as possible: 13 in the Settings tab; rows that don't apply are hidden.
3. Every downloadable model shows its size and state, can be downloaded, cancelled and removed
   from the window, with live progress, the same way for all of them.
4. "Accurate" speech to text actually runs Large v3 Turbo on the GPU.
5. Everything works: every row changes the saved setting, and Rum uses it.

## Non-goals

- Copying Superwhisper's code, name, logo or wording. Only the layout and sizes are matched.
- New features beyond the above (no vocabulary, no microphone picker, no talk-mode option here;
  those are separate requests).
- Changing the bar panel (plugin) in this work, except what's needed to keep it in sync.
- Building ZONOS3 from the window (it needs a source build; it's listed only when installed).

## Anti-goals (a failure even if it works)

- A window that's still busy: hints on every row, technical knobs, two rows for one idea.
- A download that freezes the window, can't be cancelled, or leaves a broken half model that Rum
  then tries to load.
- Losing Hazem's current values for the rows that are removed.
- Accurate silently falling back to the CPU again without saying so.

## Constraints

- Settings window: GTK4 with the system Python (`settings/omarum_settings.py`), rows described in
  `omarum/settings_model.py`, values in `~/.config/omarum/config.toml`, keys in `~/.config/omarum/env`.
- Speech models need Rum's venv (`~/.local/share/omarum/venv`, faster-whisper / huggingface_hub);
  the system Python doesn't have them. The venv is managed by `uv sync`, which removes packages it
  didn't install, so nothing may be `pip install`ed into it.
- No sudo. Downloads go under `~/.local/share/omarum/models/`.
- Keyboard-first, as now: ↑↓ select, ←→/Space change, Enter edit or act, Tab next tab, Q close.
- Theme colors from Omarchy, as now.

## Measured from the two windows (screenshots, 1.25 scale)

| | Superwhisper | Rum today | New |
|---|---|---|---|
| Text | ~12px | 14px | 12px |
| Row height | ~28px | ~33px | 28px |
| Value column from the window's left | ~180px | ~272px | 180px |
| Section title | small, bold, foreground | 13px, faded | 11px bold, foreground |
| Selected row | whole row tinted, label in accent | same + left bar | whole row tinted, label in accent, no bar |
| Switch | small drawn switch | `[■■ on ]` text | small drawn switch |
| Slider | thin line, tick handle, value right | `‹ ●── ›` | thin line, tick handle, value right |
| Buttons | capitalized, tight | lowercase | capitalized, tight |
| Hints | none (ⓘ on one row) | gray text after most rows | only the selected row's, in the footer |
| Footer | `↑/↓ Select · ←/→ or Space Change · Enter … · Q Close` | same idea | same |

## Approaches considered

1. **Restyle the existing GTK window and slim down its rows** (chosen). Keeps the keyboard handling,
   secrets handling and tests that already work; the look is CSS plus a few drawn widgets.
2. Rewrite the window in QML inside the plugin, like Superwhisper's own window being native.
   Matches Omarchy's shell, but throws away a working window and its tests for no visible gain.
3. Drop the window and put everything in the bar panel. Too little room for downloads and memory.

## The design

### Tabs

`◉ omarum   Settings   Models   Memory   Conversations`

### Settings tab (13 rows)

```
 General
   Name                 Rum
   Your name            Hazem
   Brain                ‹  Codex  ›
   API key              ••••••  ✓ works          only for brains that need one
   Model                ‹  default  ›            only for brains with more than one model
 Voice
   Voice                ‹  ZONOS3 · Default  ›   every voice of every engine, one list
   ElevenLabs key       ••••••  ✓ works          only when an ElevenLabs voice is picked
   Volume               ━━━━━━━━┃━━━  100%
 Speech to text
   Processing           [Fast] [Accurate]
 Talking
   Response speed       [Fast] [Balanced] [Patient]
   Talk key             Ctrl+Shift+Space
 Orb
   Style                [Glow] [Lines] [Ring]
   Position             ‹  Top right  ›
 Screen
   Look when I ask      [■ ]
   See my code          [■ ]
```

- **Voice list** entries: `ElevenLabs · <voice>` (only with a working key, or all with "needs key"),
  `ZONOS3 · <voice>` (only if installed), `Kokoro · <voice>`, `Piper · Amy`. Picking one sets both
  `voice_primary` and that engine's voice. A local voice that isn't downloaded shows its size,
  e.g. `Kokoro · Heart  (330 MB)`; picking it starts its download (progress in that row and in the
  Models tab) and Rum keeps using the previous voice until it finishes.
- **Processing**: Fast = Whisper Base on the CPU. Accurate = Whisper Large v3 Turbo on the GPU
  (default when a GPU is present). Choosing Accurate downloads whatever it lacks (the model and the
  GPU support files), progress shown under it; until ready, Rum keeps using Fast and the row says
  so. Without an NVIDIA GPU, Accurate is dimmed and its footer hint says why.
- **Removed rows**, values kept as they are in config.toml: Colors (classic), orb Size (160),
  Wait before answering, Ends after silence, Words needed to interrupt, Mute mic while talking,
  Whisper device (auto), Save recording audio, Export (still `omarum export` on the command line).

### Models tab (every model, same row)

```
 Speech to text
   Whisper Base              141 MB    ✓ Ready                 (always kept; Fast uses it)
   Whisper Small             464 MB    ✓ Ready      Del removes
   Whisper Large v3 Turbo    1.6 GB    ✓ Ready      (Accurate uses it)
   GPU support               ~1.0 GB   ↓ Download   needed for Accurate
 Voices
   Kokoro                    330 MB    ✓ Ready
   Piper · Amy                61 MB    ✓ Ready
   ZONOS3                    —         Installed  /  Not installed: build it, see README
```

States, the same for every row: `↓ Download` · `↓ 42%  680 MB of 1.6 GB` · `Paused  680 MB of 1.6 GB`
· `✓ Ready` · `✗ Failed: <why>  Enter to retry` · `Checking…`. Enter downloads / cancels (a cancel
keeps the partial file so the next Enter resumes it). Delete removes a ready model, asking once in
the row itself ("Delete again to remove"), and is refused for the model in use and for Base.

### How downloads work

- A catalog in `omarum/catalog.py`: id, title, group, size in bytes, files (URL, size, sha256 when
  known), and how to tell it's ready. Whisper files come from Hugging Face (Systran faster-whisper
  repos, and the mobiuslabs/deepdml turbo conversion currently used); Kokoro from the kokoro-onnx
  release; Piper from rhasspy/piper-voices; GPU support = the `nvidia-cublas-cu12` and
  `nvidia-cudnn-cu12` wheels from PyPI, unpacked (only their `.so` files) into
  `models/gpu/`, never installed into the venv.
- A command in the venv: `omarum models list --json` (every model with its state) and
  `omarum models download|cancel|remove <id>`. A download writes `<file>.part`, resumes with HTTP
  Range, checks size (and sha256 when known), then renames: a model is never half there. Progress
  is a JSON line about every 250 ms, and a small state file under `models/.state/<id>.json`, so the
  window can reopen during a download and still show it.
- The settings window runs that command as a child process (never blocking GTK) and redraws the
  row from its progress lines. Downloads continue if the window closes.
- Rum's engine loads CUDA from `models/gpu/` (adds it to the library path before loading
  faster-whisper), and `cuda_libs_loadable()` checks there too. The first-load setup downloads only
  Base and Kokoro, through the same code.

### Checking it works

- Unit tests: catalog states, resume after cancel, size/sha mismatch leaves no model, remove refuses
  the model in use, each row writes the right config key, merged voice list, hidden rows.
- In the real window: change every row and read config.toml back; download and cancel a model and
  watch the row; pick Accurate and confirm in daemon.log that Whisper runs `large-v3-turbo on cuda`;
  screenshots next to Superwhisper's at the same size.

## Calls I made (Hazem can change any)

- Models get their own tab rather than a section, to keep the Settings tab short.
- Accurate is the default on machines with an NVIDIA GPU.
- Base is always kept (it's the fallback); everything else can be removed.
- Downloads keep going when the window closes.
- ElevenLabs voices appear in the list without a key, marked "needs key", so the key row can appear.

## Left to the builder

- Exact Hugging Face repo per Whisper size, sha256s where published, the exact CUDA wheel versions
  that match ctranslate2.
- How the drawn switch and slider are made in GTK (DrawingArea or CSS on Gtk.Switch / Gtk.Scale).
- Wording of failure messages.
