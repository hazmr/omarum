"""The settings window's rows: what each one shows and how ←/→ changes it. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass

TABS = ("Companion", "Engine", "Memory", "Conversations")

FOOTERS = {
    "Companion": ["↑/↓ Select", "←/→ or Space Change", "Enter Edit", "Tab Next tab", "Q Close"],
    "Engine": ["↑/↓ Select", "←/→ or Space Change", "Enter Edit", "Tab Next tab", "Q Close"],
    "Memory": ["↑/↓ Select", "←/→ Change", "Enter Open", "D Forget", "Q Close"],
    "Conversations": ["↑/↓ Select", "Enter Play", "Space Stop", "D Delete", "Q Close"],
}


@dataclass(frozen=True)
class Row:
    tab: str
    group: str
    label: str
    key: str | None
    kind: str  # cycle | seg | toggle | slider | text | secret | shortcut | info | action
    options: tuple = ()
    hint: str = ""


ROWS: list[Row] = [
    # Companion
    Row("Companion", "Her", "Name", "companion_name", "text", hint="what you call your companion"),
    Row("Companion", "Her", "Your name", "user_name", "text"),
    Row("Companion", "Orb", "Style", "orb_style", "seg", ("glow", "lines", "ring")),
    Row("Companion", "Orb", "Position", "orb_position", "cycle",
        ("top-right", "top-center", "top-left", "center", "bottom-center")),
    Row("Companion", "Orb", "Colors", "orb_colors", "cycle", ("theme", "warm", "glass", "mono")),
    Row("Companion", "Orb", "Size", "orb_size", "slider", (96, 320, 16, "px")),
    Row("Companion", "Conversation", "Ends after silence", "idle_timeout_secs", "slider", (4, 30, 2, "s")),
    Row("Companion", "Conversation", "Words needed to interrupt", "interrupt_min_words", "slider", (1, 6, 1, "")),
    Row("Companion", "Conversation", "Mute mic while talking", "mute_while_speaking", "toggle",
        hint="stops your companion hearing itself through the speakers"),
    Row("Companion", "Shortcuts", "Talk (hold) / hands-free (tap)", "talk_shortcut", "shortcut",
        hint="Enter, then press the new keys"),
    Row("Companion", "Shortcuts", "Open settings", "settings_shortcut", "shortcut", hint="optional"),
    # Engine
    Row("Engine", "Brain", "Model", "brain_model", "seg", ("haiku", "sonnet", "opus"),
        hint="through your own claude CLI"),
    Row("Engine", "Voice", "Engine", "voice_primary", "seg", ("elevenlabs", "zonos3", "kokoro"),
        hint="falls back down this order if it fails"),
    Row("Engine", "Voice", "ZONOS3 voice", "zonos3_voice", "cycle",
        ("Savannah", "Willow", "Imogen", "Wyatt", "Rupert", "Cillian", "Jett")),
    Row("Engine", "Voice", "Kokoro voice", "kokoro_voice", "cycle",
        ("af_heart", "af_bella", "af_nicole", "bf_emma", "am_michael", "bm_george")),
    Row("Engine", "Voice", "Voice volume", "voice_volume", "slider", (50, 300, 10, "%")),
    Row("Engine", "Voice", "ElevenLabs key", "ELEVENLABS_API_KEY", "secret", hint="Enter to set, empty to remove"),
    Row("Engine", "Ears", "Whisper device", "whisper_device", "seg", ("auto", "cuda", "cpu")),
    # Memory
    Row("Memory", "Privacy", "Save recording audio", "record_audio", "toggle"),
    Row("Memory", "Privacy", "Keep conversations", "retention_days", "cycle", (0, 7, 30, 90, 365)),
    Row("Memory", "Privacy", "Export everything", None, "action", hint="a .tar.gz in your home folder"),
]


def row(key: str) -> Row:
    return next(r for r in ROWS if r.key == key)


def rows_for(tab: str) -> list[Row]:
    return [r for r in ROWS if r.tab == tab]


def display(r: Row, value) -> str:
    if r.kind == "shortcut":
        return " + ".join(p.capitalize() for p in value.split(" + ")) if value else "none"
    if r.kind == "toggle":
        return "on" if value else "off"
    if r.kind == "secret":
        return "set ✓" if value else "not set"
    if r.key == "retention_days":
        return "Forever" if not value else f"{value} days"
    if r.kind == "slider":
        unit = r.options[3]
        return f"{value:g}{unit}" if isinstance(value, float) else f"{value}{unit}"
    return str(value)


def step(r: Row, value, direction: int):
    if r.kind == "toggle":
        return not value
    if r.kind in ("cycle", "seg"):
        opts = r.options
        i = opts.index(value) if value in opts else 0
        if r.kind == "cycle":
            return opts[(i + direction) % len(opts)]
        return opts[max(0, min(len(opts) - 1, i + direction))]
    if r.kind == "slider":
        lo, hi, inc, _unit = r.options
        new = max(lo, min(hi, value + direction * inc))
        return float(new) if isinstance(value, float) else int(new)
    return value
