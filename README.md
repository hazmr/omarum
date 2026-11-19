# Omarum

A voice companion for [Omarchy](https://omarchy.org). Press a shortcut, a small glowing orb appears, you talk, and **Rum** answers out loud. There's no chat window and no text, only the orb and two voices.

> **Status: phases 1–4 of 5 done.** It works on the author's machine; proper packaging (autostart, Omarchy menu, AUR) is next. See [the design](docs/superpowers/specs/2026-11-18-omarum-design.md).

## What works today

- **Hold Ctrl + Shift + Space** to talk: Rum stops mid-sentence the moment you press (interrupt), listens while you hold, and answers when you let go. **Tap** it for hands-free mode, tap again to close. Rum also closes after 8 seconds of silence. Change the keys in `omarum settings` → Shortcuts.
- **Memory:** every conversation is saved locally (both voices + transcript). Rum updates plain-text notes about you after each talk, writes a daily journal, and starts every conversation knowing them.
- **Settings:** `omarum settings` opens a keyboard-first window (Companion · Engine · Memory · Conversations) to change everything below, forget facts, and play back or delete conversations.
- **The orb** (GTK4 layer-shell overlay) follows the conversation: your color while you talk, Rum's while Rum talks. Three styles (glow, lines, ring), five positions (center dims the screen), any size, colors from your Omarchy theme (updates live when you switch themes) or Warm/Glass/Mono.
- **Ears:** Whisper runs locally (large-v3-turbo on an NVIDIA GPU, base.en on CPU).
- **Brain:** your own logged-in Claude Code CLI (`claude -p`), using your existing subscription, for personal use.
- **Voice:** you pick one, and if it fails, Rum moves down this order:
  1. **ElevenLabs** (cloud, needs `ELEVENLABS_API_KEY` in `~/.config/omarum/env`)
  2. **ZONOS3-Mini** (local, Apache 2.0, runs on CPU or any Vulkan GPU)
  3. **Kokoro** (local, always available)
- Noise doesn't interrupt Rum, the mic is muted while Rum speaks (until echo cancellation lands), and Rum restarts itself after a crash.

## Install

Omarum is one Omarchy plugin: the bar button and panel, the orb, the talk shortcut and Rum's voice engine.

```bash
omarchy plugin add https://github.com/hazmr/omarum
```

Requirements: Omarchy, [uv](https://docs.astral.sh/uv/) (`omarchy pkg add uv`), and a brain you're logged into or have a key for (the `claude` CLI is the default). The first load sets up Rum's Python environment in `~/.local/share/omarum/venv` and downloads the models it needs (Whisper base.en, Kokoro); the panel shows the progress. After that Rum starts with the Omarchy shell and restarts itself after a crash.

- **Talk:** hold Ctrl+Shift+Space to talk, tap it for hands-free (change it in settings). The plugin binds the key itself while it's loaded.
- **Bar:** click the orb for the panel (hands-free, the brain, your last conversation, settings); right-click toggles hands-free; middle-click opens settings.
- **Remove:** `omarchy plugin remove omarum.panel` stops Rum, the orb and the shortcut. Your conversations, memory and settings stay in `~/.local/share/omarum` and `~/.config/omarum`; delete those folders to remove them too.

Upgrading from the old installer: the first load stops and removes the old systemd services, shortcut file, menu entries, theme hook and `omarum` command for you.

ZONOS3-Mini (an optional local voice) is built by hand from [Zyphra/ZONOS3-Mini](https://github.com/Zyphra/ZONOS3-Mini) into `~/.local/share/omarum/engines/zonos3` (see its README: `cmake -B build-vulkan -DGGML_VULKAN=ON && cmake --build build-vulkan`, then `hf download Zyphra/ZONOS3-Mini` for the `gguf/` files); Rum uses it when it's there.

Settings live in `~/.config/omarum/config.toml`, for example:

```toml
companion_name = "Rum"
voice_primary = "zonos3"     # elevenlabs | zonos3 | kokoro
zonos3_voice = "Savannah"
kokoro_voice = "af_heart"
```

Logs: `~/.local/state/omarum/daemon.log`.

## Development

```bash
uv run pytest
ln -s "$PWD" ~/.config/omarchy/plugins/omarum.panel   # run your checkout as the plugin
omarchy-shell shell rescanPlugins && omarchy plugin enable omarum.panel
```

The plugin (`plugin/`, QML) runs the daemon (`omarum/`, Python 3.12, [Pipecat](https://github.com/pipecat-ai/pipecat)) as a child process and talks to it over a Unix socket (`omarum/ipc.py`). The settings window (`settings/`) is system Python with GTK4.

## Roadmap

1. ✅ Prototype: talk, orb, voices
2. ✅ Memory: Rum remembers you day to day; conversations are recorded locally
3. ✅ The full orb: three styles, positions, palettes, live theme
4. ✅ A keyboard-first settings app in Omarchy's style
5. ✅ Any brain: any subscription CLI or any API
6. ✅ One plugin: install and remove with `omarchy plugin add` / `remove`
