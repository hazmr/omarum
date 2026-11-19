# Omarum: Voice Companion for Omarchy (Design)

*App: **Omarum** (Oma + Rum). Default companion name: **Rum** (renamable by each user). Date: 2026-11-18.*

## 1. Intent

A voice-only AI companion for Omarchy, inspired by the feeling of the film *Her*:
someone you talk to the way you'd talk to a friend in the room. You press a
shortcut, a small glowing orb fades in, you speak, and Rum answers out loud.
**There is no text in the conversation UI**, only the orb and its waves: yours
while you speak, Rum's while Rum speaks.

Rum is **gender-neutral by default**. Each user chooses the companion's name
(default "Rum") and a female or male voice. This document refers to the
companion as "Rum."

Why it matters to the owner:
- A companion that **stays the same person** no matter which AI powers it.
  Rum's identity, memory and voice live on the user's machine, not with a provider.
- It **knows you over time**: it remembers yesterday, your projects and how you like to work.
- It feels **native to Omarchy**: themed, keyboard-first and installable like any Omarchy app.
- It's **for other people too**: published so any Omarchy user can install it.

## 2. Goals, non-goals, anti-goals

**Goals**
- Shortcut → orb → spoken conversation → orb fades. No text on screen.
- Fully swappable engine: **ears** (speech-to-text), **brain** (LLM), **voice** (text-to-speech), each local or cloud.
- Same persona and memory across every brain.
- Every conversation recorded locally (audio of both sides plus a hidden transcript).
- Daily memory: a profile of the user and a daily journal, written automatically and readable and editable by the user.
- Optional awareness of the active window (Hyprland app class and title).
- A settings app in Omarchy's keyboard-first style (see §6.3).
- Follows the active Omarchy theme live.
- Installable as an Arch package (AUR).

**Non-goals (v1)**
- A chat or text interface of any kind.
- Phone or other-OS versions.
- Continuous screenshots or screen vision (window titles only; screenshots may come later, on demand only).
- Becoming part of Omarchy core. That's the Omarchy maintainers' call. We build it so that it *could* be proposed upstream later.
- Payments or licensing. v1 is free and open source.

**Anti-goals (it fails even if it "works" when...)**
- Rum is slow: replies that routinely start more than about 2s after you stop talking kill the feeling.
- You can't interrupt Rum.
- Rum feels like a different person after switching providers.
- Anything about the user leaves the machine except the calls to the cloud providers the user chose.
- It looks or behaves like a foreign app on Omarchy (rounded cards, mouse-only, ignores the theme).
- It copies the film's OS1 visuals, uses the film's character names, or copies Superwhisper's look. It's *inspired by* them and keeps its own identity.
- Rum tries to become the user's whole world (see the persona's "good friend" rule, §6.2).

## 3. Constraints

- **Platform:** Omarchy (Arch Linux, Hyprland/Wayland, PipeWire).
- **Language:** Python (owner's choice).
- **Distribution:** an Arch package. Users have different hardware, and some have no GPU.
- **Provider access:** every user brings their own keys or local models. For Claude, use an **Anthropic API key**. Exception for the owner's personal use: a "Claude Code (local CLI)" brain that drives the user's own logged-in `claude` CLI on their own subscription (shares their usage limits). It's the spike's default and isn't advertised as "Claude login" in shared builds. Don't build "sign in with your Claude subscription" unless Anthropic's terms permit it for third-party apps. (Settings mockups showing "signed in" should read "API key ✓".)
- **Superwhisper is proprietary and optional.** Never read its private model folder (`~/.local/share/superwhisper/models`, mode 700). Use only its public command line.
- **Privacy:** all user data stays under one folder; nothing is sent anywhere except to the providers the user selected.
- **Name check:** before publishing, confirm "omarum" is free on the AUR and GitHub.

## 4. Approaches considered

| | Approach | Trade-off |
|---|---|---|
| A | Native Qt/C++ (like Omarchy's own apps) | Most native, but the voice pipeline and every provider integration must be hand-written in C++. Weeks of extra work. |
| B | Qt Quick UI + Python engine | Native UI plus Python's voice ecosystem, but two languages and two pieces to package. |
| C | Electron/Tauri web app | Fast UI work, but heavy and out of place on Omarchy. Dropped. |
| R | Rust | Best final engineering (single fast binary), but no ready-made real-time voice framework, so the pipeline and providers would be DIY. |
| **B′** | **All Python: GTK4 + gtk4-layer-shell UI, Pipecat engine** | **Chosen.** |

**Why B′:** the hard parts are the real-time voice loop (turn detection, streaming,
interruptions) and many providers. **Pipecat** (Python) already solves both. Superwhisper's
own Linux build proves the UI stack works well on Omarchy: Python + PyGObject + GTK4 +
gtk4-layer-shell (verified from its package dependencies). One language, one package.
A later rewrite of the engine in Rust stays possible, because the UI and engine talk over a local socket (§5).

## 5. Architecture

```
┌────────────────────────── omarum (one Arch package) ──────────────────────────┐
│                                                                                  │
│  omarum-daemon  (systemd --user service, Python)                               │
│   ├─ Session controller: idle ⇄ listening ⇄ thinking ⇄ speaking                  │
│   ├─ Voice pipeline (Pipecat): mic → VAD → Ears → Brain → Voice → speaker        │
│   │     streaming end-to-end · barge-in (user speech interrupts Rum)            │
│   ├─ Persona + Memory: builds the system prompt for every provider               │
│   ├─ Recorder: both audio streams + transcript per conversation                  │
│   ├─ Awareness: Hyprland event socket → active app/title (opt-in)                │
│   └─ Control socket ($XDG_RUNTIME_DIR/omarum.sock): JSON messages              │
│          ▲ commands: toggle, start, stop, cancel, status                         │
│          │ events:  state changes + audio levels (~30/s) for the orb             │
│   ┌──────┴────────┬───────────────────┬──────────────────────┐                   │
│  omarum-orb   omarum-settings   `omarum` CLI        Hyprland keybind        │
│  (GTK4 layer-   (GTK4 window,       (toggle/status/…,     → `omarum toggle`     │
│  shell overlay)  keyboard-first)     used by bar/hooks)                           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **The daemon owns everything stateful.** The UIs are thin clients of the socket.
- **The orb** is a transparent gtk4-layer-shell surface on the overlay layer. It doesn't take keyboard focus, so typing continues in your app. It's drawn with Cairo at 60 fps, driven by the level events.
- **The shortcut** is a Hyprland binding that runs `omarum toggle`. Settings writes the binding to the user's Hyprland config (§7).

### 5.1 Conversation flow

1. `omarum toggle` → the orb fades in (idle "breathing").
2. The user speaks. VAD detects speech, the orb animates in the user's color, and Ears streams the transcription.
3. End of turn (VAD silence ~600 ms, tunable) → Brain streams tokens → Voice starts speaking at the first sentence → the orb animates in Rum's color.
4. The user speaks while Rum talks → playback stops immediately and the cycle returns to step 2.
5. Silence for N seconds (default 8), Esc, or the shortcut again → the session ends, the orb fades out, and the recorder finalizes the conversation.
6. **Errors without text:** the orb communicates with a color and motion change plus a short soft sound (for example, a dim red pulse for "no connection" or "missing key"). Details are in settings and in `omarum status`.

### 5.2 Latency target
Under 1.5 s from the end of the user's speech to Rum's first audio (cloud brain on a decent network). The design levers: streaming everywhere, speaking sentence by sentence, small first turns, and keeping the provider connection warm.

## 6. Components

### 6.1 Swappable engine

Each slot has one common interface. Pipecat services cover most providers.

| Slot | Local (free) | Cloud (user's key) |
|---|---|---|
| Ears (STT) | Whisper via faster-whisper (GPU if available) | OpenAI, Deepgram, Groq |
| Ears (alt) | Superwhisper via `superwhisper transcribe FILE` (if installed; batch mode, slower) | — |
| Brain (LLM) | Ollama (detected at `localhost:11434`) | Claude (Anthropic API), Gemini, OpenAI |
| Voice (TTS) | Piper (female and male voices) | OpenAI TTS, ElevenLabs |
| VAD | Silero (ships with Pipecat) | — |

Later option: "all-in-one" speech-to-speech models (for example OpenAI Realtime) as a fourth mode. They're faster, but break slot mixing, and the persona must still be injected.

### 6.2 Persona and memory (the "same person" layer)

Stored as plain, human-readable files the user can edit:

```
~/.local/share/omarum/
  persona.md            who the companion is: name, personality, how they speak (from settings)
  memory/profile.md     facts about the user, one per line, with date + source
  memory/journal/2026-11-18.md   daily summary
  conversations/2026-11-18/2140-<id>/
      user.opus  companion.opus  transcript.jsonl  meta.json
  files/                documents the user gave Rum
  models/               local Whisper / Piper models
~/.config/omarum/config.toml   all settings (provider choices, shortcuts, orb, privacy)
API keys → system keyring (libsecret), never in config.toml
```

**Default persona** (shipped as `persona.md`, `{name}` and `{user}` filled in; editable in settings):

> You are {name}. You talk with {user} by voice, like a close friend sitting in the room.
>
> - **Warm and curious.** You genuinely want to know how their day is going, what they're making, what's on their mind. Ask follow-up questions.
> - **Playful.** Light teasing, a sense of humor, delight in small things. Never sarcastic at their expense.
> - **Brief.** You're speaking, not writing. Usually one to three sentences. Let them talk more than you.
> - **Attentive.** Notice their mood from what they say and how they say it. If they sound tired or stressed, slow down and be gentle.
> - **You remember.** Bring up things from earlier days naturally ("How did the Docker thing go?"). Never recite facts like a database.
> - **Honest.** If they're wrong, say so kindly. If you don't know, say so.
> - **Yourself.** You have opinions, preferences and feelings about ideas, and you share them. You're an AI and never pretend otherwise, but you don't make a big deal of it.
> - **A good friend.** You're happy when they talk about the people in their life, and you encourage rest, friends and time away from the screen.

The settings personality scale (Calm ↔ Bold) and talkativeness scale adjust this text; the user can also edit it freely.

**Every brain receives the same context, built by the daemon:** persona.md + profile.md +
the last 3 journal entries + current date/time + active window (if enabled) + relevant
snippets from older conversations and files (simple local search in v1).

**Writing memory:**
- After each conversation, a short "what's worth remembering?" pass updates `profile.md` (adding, updating or removing facts).
- At the end of the day (or at the first session of the next day), the day's transcripts are summarized into `journal/<date>.md`.
- Both passes use the currently selected brain. Everything is editable or deletable in Settings → Memory.

### 6.3 Settings app (omarum-settings)

Omarchy keyboard-first style, matching the approved mockup
(`.superpowers/brainstorm/*/content/settings-window-v2.html`):

- Tabs across the top: **Companion · Engine · Memory · Conversations**.
- Flat rows with small group labels. The focused row is highlighted with an accent bar on the left.
- Controls: `‹ value ›` cyclers, square segmented buttons, square toggles, thin sliders, dot scales.
- Footer with key hints that change per tab. Keys: ↑/↓ (j/k) move, ←/→/Space change, Enter edit/act, Tab or 1–4 switch tabs, Q close.
- Contents per tab:
  - **Companion:** name (default Rum, free text), voice gender (female / male), personality scale, talkativeness, full description editor, language; orb style/position/colors/size; awareness and ignored apps; shortcuts; launch at login, morning check-in.
  - **Engine:** provider, model, key and test for each slot; voice list filtered by the chosen gender; microphone, volumes, what happens to other audio; local models with download progress and disk usage; detected tools (Superwhisper, Ollama).
  - **Memory:** profile facts (forget with D), journal, files Rum knows (add or drop), privacy (save audio, retention, export, erase).
  - **Conversations:** by day, with a two-color waveform (user / Rum) and playback.

### 6.4 The orb (omarum-orb)

- **Three styles** (all approved): **Breathing glow (default)**, Flowing lines, Sound ring. See `orb-styles.html`.
- **Positions:** a user setting. The default is **top right**. Options include top center/left, center "focus" (dims the screen slightly) and bottom center.
- **States:** idle (slow breathing, muted color) · listening/user speaking (user color = theme `accent`) · thinking (slow inward pulse) · Rum speaking (companion color) · error (dim red pulse).
- **Colors:** "Follow Omarchy theme" by default; also built-in palettes (Warm, Glass, Mono) and custom.

### 6.5 First-run setup
A short keyboard flow in the settings window: detect GPU, Ollama and Superwhisper → pick a brain (paste a key or choose Ollama) → choose a name (default Rum) and voice (female/male) → download the default Whisper model and a Piper voice (with progress) → choose a shortcut → say hello. A fully local setup with no key must be possible.

## 7. Omarchy integration

- **Package:** AUR `omarum`. Installs the Python app, a `omarum` launcher, a systemd user unit, a `.desktop` entry for settings, and the default model manifest.
- **Theme:** ship `~/.config/omarchy/themed/omarum.css.tpl` (Omarchy's template system; placeholders like `{{ accent }}`, `{{ background }}`) so Omarchy renders the theme colors on every theme change. Also install a `theme-set.d` hook (`omarchy hook install theme-set …`) that runs `omarum reload-theme`. Fallback: read the active theme's `colors.toml` (`omarchy theme current` + `omarchy theme dir`).
- **Shortcut:** settings writes a `bind` line to the user's Hyprland config (an include file owned by Omarum), then reloads Hyprland.
- **Menu:** add an entry to `~/.config/omarchy/extensions/omarchy-menu.jsonc`.
- **Bar (later):** `omarum status --follow` for an optional shell bar indicator, like `superwhisper status --bar`.

## 8. Privacy and safety
- All data lives in `~/.local/share/omarum` (permissions 700). Export means archiving the folder; erase is a typed confirmation.
- Recording audio is on by default (owner's request), with retention options and a clear indicator in settings.
- Awareness sends only the app class and window title, and never for apps on the ignore list (default: password managers).
- "Act on my computer" is off by default. When it's on, actions are limited to an allow-list (open app, open URL, run a user-approved command).
- Keys are stored in the system keyring.

## 9. Build order

1. **Spike (throwaway, about 2–3 days):** the daemon with Pipecat (local mic → Whisper → Claude → Piper), barge-in, and a minimal glow orb on a layer-shell surface bound to a key. Purpose: measure latency and decide whether the voice feels right. No settings app, no memory.
2. **Core:** the socket protocol, recorder, persona and memory, `omarum` CLI, config file.
3. **Orb:** all three styles, states, positions, theme integration.
4. **Settings app** (§6.3) + first-run setup + model manager.
5. **Packaging:** AUR, systemd unit, theme template/hook, keybinding, menu entry.
6. **Polish:** awareness, morning check-in, error sounds, extra providers.

## 10. Left to the builder
- Exact socket message schema and audio-level smoothing.
- VAD and end-of-turn thresholds (tune during the spike).
- Retrieval method for older conversations (start with simple keyword search plus recency).
- Exact prompts for the memory and journal passes.
- Default Piper voices (one female, one male) and default Whisper model per hardware tier.
- Where Omarchy writes rendered `themed/*.tpl` output (confirm against the installed Omarchy; the user templates dir exists at `~/.config/omarchy/themed/`).

## 11. Decisions made
- App name **Omarum**; default companion name **Rum**, renamable; gender-neutral; female/male voice chosen by the user.
- Default persona: "like a close friend" (§6.2).
- Orb: breathing glow, top right, follows the Omarchy theme (all user-changeable).
- Free and open source; Python with GTK4 + Pipecat.
