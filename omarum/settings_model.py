"""The settings window's rows: what each one shows and how ←/→ changes it. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass

from omarum.brains import PROVIDERS

TABS = ("Companion", "Engine", "Memory", "Conversations")


def tab_index(name: str) -> int:
    """`omarum settings conversations` opens on that tab; anything else opens the first."""
    names = [t.lower() for t in TABS]
    return names.index(name.lower()) if name.lower() in names else 0

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
    kind: str  # cycle | seg | toggle | slider | text | secret | shortcut | info | action | model
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
    # Engine
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


def brain_rows(brain: str, brain_status=None) -> list[Row]:
    """The Brain group for the chosen provider: which brain, its model, and what it needs."""
    p = PROVIDERS.get(brain, PROVIDERS["claude-code"])
    state = brain_status(p) if brain_status else ""
    if p.kind == "cli" and state == "ready":
        state = "installed (log in to it once: " + p.login_hint + ")"
    how = "your own logged-in CLI" if p.kind == "cli" else ("runs on this computer" if p.group == "Local" else "your API key")
    rows = [
        Row("Engine", "Brain", "Brain", "brain", "cycle", tuple(PROVIDERS),
            hint=f"{how}" + (f" · {state}" if state else "") + (f" · then: {p.login_hint}" if p.kind == "cli" and state not in ("", "ready") else "")),
        Row("Engine", "Brain", "Model", "brain_model", "model", tuple(m for m in p.models) or ("",),
            hint="←/→ suggestions · Enter to type any model name"),
    ]
    if p.id == "custom":
        rows.append(Row("Engine", "Brain", "Endpoint", "brain_url", "text",
                        hint="an OpenAI-compatible URL, e.g. http://localhost:1234/v1"))
    if p.env_key:
        rows.append(Row("Engine", "Brain", "API key", p.env_key, "secret",
                        hint=f"{p.env_key} · Enter to set, empty to remove" + (" (optional)" if p.id == "custom" else "")))
    return rows


def rows_for(tab: str, brain: str = "claude-code", brain_status=None) -> list[Row]:
    rows = [r for r in ROWS if r.tab == tab]
    return brain_rows(brain, brain_status) + rows if tab == "Engine" else rows


def display(r: Row, value) -> str:
    if r.key == "brain":
        p = PROVIDERS.get(value, PROVIDERS["claude-code"])
        return f"{p.label} ({p.group.lower()})"
    if r.kind == "model":
        return value or "default"
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
    if r.kind == "model":
        opts = r.options
        return opts[(opts.index(value) + direction) % len(opts)] if value in opts else opts[0]
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


def once(fn):
    """For GLib.idle_add: run fn one time. (GLib repeats a callback that returns True, and
    grab_focus() returns True, so idle_add(entry.grab_focus) would grab focus forever.)"""
    def run(*_args):
        fn()
        return False
    return run


EDIT_KEYS = {"Escape": ("cancel", 0), "Down": ("save", +1), "Up": ("save", -1),
             "Tab": ("save", +1), "ISO_Left_Tab": ("save", -1)}


def edit_key(name: str):
    """What a key does while a text field is open: (action, move) or None (the field keeps it)."""
    return EDIT_KEYS.get(name)
