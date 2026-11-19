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
- Noise doesn't interrupt Rum, the mic is muted while Rum speaks (until echo cancellation lands), and the service restarts itself after a crash.

## Try it (prototype)

Requirements: Omarchy (Hyprland, PipeWire), [uv](https://docs.astral.sh/uv/), the `claude` CLI logged in, and the system packages `gtk4-layer-shell`, `python-gobject` and `portaudio`.

```bash
git clone https://github.com/hazmr/omarum.git && cd omarum
uv sync
bash scripts/spike-install.sh   # puts `omarum` on PATH, binds Ctrl+Shift+Space, starts the daemon and the orb
```

Models download into `~/.local/share/omarum/` (Whisper, Kokoro). ZONOS3-Mini is optional and built from [Zyphra/ZONOS3-Mini](https://github.com/Zyphra/ZONOS3-Mini) into `~/.local/share/omarum/engines/zonos3`.

Settings live in `~/.config/omarum/config.toml`, for example:

```toml
companion_name = "Rum"
voice_primary = "zonos3"     # elevenlabs | zonos3 | kokoro
zonos3_voice = "Savannah"
kokoro_voice = "af_heart"
```

Useful commands: `omarum status`, `omarum toggle`. Logs are in `~/.local/state/omarum/`.

## Development

```bash
uv run pytest
```

The daemon (`omarum/`, Python 3.12, [Pipecat](https://github.com/pipecat-ai/pipecat)) and the orb (`orb/`, system Python with GTK4) talk over a Unix socket (`omarum/ipc.py`).

## Roadmap

1. ✅ Prototype: talk, orb, voices
2. ✅ Memory: Rum remembers you day to day; conversations are recorded locally
3. ✅ The full orb: three styles, positions, palettes, live theme
4. ✅ A keyboard-first settings app in Omarchy's style
5. Packaging: systemd user service, Omarchy menu entry, AUR
