"""The settings window's rows: what each one shows and how ←/→ changes it. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass

from omarum.brains import PROVIDERS

TABS = ("Settings", "Models", "Memory", "Conversations")
_OLD_TABS = {"companion": 0, "engine": 0}


def tab_index(name: str) -> int:
    """`omarum settings models` opens on that tab; old tab names and anything else open Settings."""
    names = [t.lower() for t in TABS]
    key = name.lower()
    return names.index(key) if key in names else _OLD_TABS.get(key, 0)


FOOTERS = {
    "Settings": ["↑/↓ Select", "←/→ or Space Change", "Enter Edit", "Q Close"],
    "Models": ["↑/↓ Select", "Enter Download / Cancel", "D Remove", "Q Close"],
    "Memory": ["↑/↓ Select", "←/→ Change", "Enter Open", "D Forget", "Q Close"],
    "Conversations": ["↑/↓ Select", "Enter Play", "Space Stop", "D Delete", "Q Close"],
}


@dataclass(frozen=True)
class Row:
    tab: str
    group: str
    label: str
    key: str | None
    kind: str  # cycle | seg | toggle | slider | text | secret | shortcut | model | voice
    options: tuple = ()
    hint: str = ""  # shown in the footer while the row is selected
    labels: tuple = ()  # (value, shown name) pairs, when values are ids


ZONOS3_VOICES = ("Savannah", "Willow", "Imogen", "Wyatt", "Rupert", "Cillian", "Jett")
KOKORO_VOICES = ("af_heart", "af_bella", "af_nicole", "bf_emma", "am_michael", "bm_george")

_NAME = Row("Settings", "General", "Name", "companion_name", "text", hint="what you call your companion")
_YOU = Row("Settings", "General", "Your name", "user_name", "text")
_ELEVEN_KEY = Row("Settings", "Voice", "ElevenLabs key", "ELEVENLABS_API_KEY", "secret",
                  hint="Enter, paste your key (starts with sk_), Enter · elevenlabs.io → Profile → API keys")
_VOLUME = Row("Settings", "Voice", "Volume", "voice_volume", "slider", (50, 300, 10, "%"))
_AFTER_VOICE = [
    Row("Settings", "Speech to text", "Processing", "whisper_device", "seg", ("cpu", "auto"),
        hint="Fast: small model on the CPU · Accurate: Large v3 Turbo on your GPU",
        labels=(("cpu", "Fast"), ("auto", "Accurate"))),
    Row("Settings", "Talking", "Response speed", "response_speed", "seg", ("fast", "balanced", "patient"),
        hint="Fast answers sooner · Patient waits longer · hold Space to always finish"),
    Row("Settings", "Talking", "Talk key", "talk_shortcut", "shortcut",
        hint="double tap: open / close · hold: talk   (Enter to change)"),
    Row("Settings", "Orb", "Style", "orb_style", "seg", ("glow", "lines", "ring")),
    Row("Settings", "Orb", "Position", "orb_position", "cycle",
        ("top-right", "top-center", "top-left", "center", "bottom-center")),
    Row("Settings", "Screen", "Look when I ask", "screen_look", "toggle",
        hint="\"look at my screen\": one screenshot, sent to your brain"),
    Row("Settings", "Screen", "See my code", "screen_awareness", "toggle",
        hint="with IntelliJ or VS Code focused, Rum reads that file (sent to your brain)"),
]
_MEMORY = [Row("Memory", "Conversations", "Keep conversations", "retention_days", "cycle", (0, 7, 30, 90, 365))]

# Every fixed row (brain and voice rows depend on the current settings; see rows_for).
ROWS: list[Row] = [_NAME, _YOU, _ELEVEN_KEY, _VOLUME, *_AFTER_VOICE, *_MEMORY]


def row(key: str) -> Row:
    return next(r for r in ROWS if r.key == key)


def brain_rows(brain: str, brain_status=None) -> list[Row]:
    """The brain rows for the chosen provider: which brain, then only what it needs."""
    p = PROVIDERS.get(brain, PROVIDERS["claude-code"])
    state = brain_status(p) if brain_status else ""
    if p.kind == "cli" and state == "ready":
        state = "installed (log in to it once: " + p.login_hint + ")"
    how = "your own logged-in CLI" if p.kind == "cli" else ("runs on this computer" if p.group == "Local" else "your API key")
    rows = [Row("Settings", "General", "Brain", "brain", "cycle", tuple(PROVIDERS),
                hint=f"{how}" + (f" · {state}" if state else "")
                + (f" · then: {p.login_hint}" if p.kind == "cli" and state not in ("", "ready") else ""))]
    if len(p.models) > 1:
        rows.append(Row("Settings", "General", "Model", "brain_model", "model", tuple(p.models),
                        hint="←/→ suggestions · Enter to type any model name"))
    if p.id == "custom":
        rows.append(Row("Settings", "General", "Endpoint", "brain_url", "text",
                        hint="an OpenAI-compatible URL, e.g. http://localhost:1234/v1"))
    if p.env_key:
        rows.append(Row("Settings", "General", "API key", p.env_key, "secret",
                        hint=f"{p.env_key} · Enter to set, empty to remove" + (" (optional)" if p.id == "custom" else "")))
    return rows


def _kokoro_name(v: str) -> str:
    return v.split("_", 1)[-1].capitalize()


def voice_options(zonos3: bool, eleven_voices, kokoro_voices=KOKORO_VOICES,
                  zonos3_voices=ZONOS3_VOICES) -> list[tuple[str, str]]:
    """Every voice of every engine, as ("engine:voice", "Engine · Name"), in fallback order."""
    from omarum.elevenlabs import DEFAULT_VOICES

    eleven = list(eleven_voices or []) or DEFAULT_VOICES
    out = [(f"elevenlabs:{v[0]}", f"ElevenLabs · {v[1]}") for v in eleven]
    if zonos3:
        out += [(f"zonos3:{v}", f"ZONOS3 · {v}") for v in zonos3_voices]
    out += [(f"kokoro:{v}", f"Kokoro · {_kokoro_name(v)}") for v in kokoro_voices]
    out.append(("piper:amy", "Piper · Amy"))
    return out


_VOICE_KEYS = {"elevenlabs": "elevenlabs_voice_id", "zonos3": "zonos3_voice", "kokoro": "kokoro_voice"}


def voice_value(values: dict) -> str:
    engine = values.get("voice_primary", "kokoro")
    if engine == "piper":
        return "piper:amy"
    return f"{engine}:{values.get(_VOICE_KEYS.get(engine, ''), '')}"


def voice_updates(choice: str) -> dict:
    engine, _, voice = choice.partition(":")
    out = {"voice_primary": engine}
    if engine in _VOICE_KEYS:
        out[_VOICE_KEYS[engine]] = voice
    return out


def rows_for(tab: str, values: dict | None = None, brain_status=None, eleven_voices=None,
             zonos3: bool = False) -> list[Row]:
    values = values or {}
    if tab == "Memory":
        return list(_MEMORY)
    if tab != "Settings":
        return []
    opts = voice_options(zonos3, eleven_voices)
    voice = Row("Settings", "Voice", "Voice", "voice", "voice", tuple(v for v, _ in opts),
                hint="every voice Rum has · a local voice not downloaded yet shows its size",
                labels=tuple(opts))
    rows = [_NAME, _YOU, *brain_rows(values.get("brain", "claude-code"), brain_status), voice]
    if values.get("voice_primary") == "elevenlabs":
        rows.append(_ELEVEN_KEY)
    return rows + [_VOLUME, *_AFTER_VOICE]


def display(r: Row, value) -> str:
    if r.labels:
        shown = dict(r.labels).get(value)
        if shown:
            return shown
        return value.split(":", 1)[-1] if r.kind == "voice" and value else ("default voice" if value else "—")
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
    if r.kind in ("seg", "cycle") and isinstance(value, str):
        return value.replace("-", " ").capitalize()
    return str(value)


def step(r: Row, value, direction: int):
    if r.kind == "toggle":
        return not value
    if r.kind == "model":
        opts = r.options
        return opts[(opts.index(value) + direction) % len(opts)] if value in opts else opts[0]
    if r.kind in ("cycle", "seg", "voice"):
        opts = r.options
        i = opts.index(value) if value in opts else 0
        if r.kind in ("cycle", "voice"):
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


# "Response speed": each preset sets how long Rum waits after you stop talking (the smart-turn
# model still waits longer when your sentence sounds unfinished) and which speech model runs.
SPEED_PRESETS = {
    "fast": {"vad_stop_secs": 0.3, "whisper_cpu_model": "tiny.en"},       # ~1 s sooner than patient
    "balanced": {"vad_stop_secs": 0.5, "whisper_cpu_model": "base.en"},
    "patient": {"vad_stop_secs": 0.8, "whisper_cpu_model": "base.en"},
}


def speed_of(values: dict) -> str:
    """Which preset the current values match, or "custom"."""
    for name, preset in SPEED_PRESETS.items():
        if all(values.get(k) == v for k, v in preset.items()):
            return name
    return "custom"


def human_size(n: int) -> str:
    if not n:
        return "—"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} GB"
    return f"{round(n / 1_000_000)} MB"


def model_status(s: dict) -> str:
    """The Models tab's state text for one model (from `omarum models list --json`)."""
    state, done, total = s.get("state"), int(s.get("done") or 0), int(s.get("total") or 0)
    if state == "ready":
        return "✓ Ready" + ("  (in use)" if s.get("in_use") else "")
    if state == "downloading":
        pct = round(done * 100 / total) if total else 0
        return f"↓ {pct}%  {human_size(done)} of {human_size(total)}"
    if state == "partial":
        return f"Paused  {human_size(done)} of {human_size(total)}"
    if state == "failed":
        return f"✗ Failed: {s.get('error') or 'unknown error'}  Enter to retry"
    return "↓ Download"


def shown_value(r: Row, values: dict):
    """The value a row shows, mapping settings saved before the redesign onto today's buttons."""
    value = values.get(r.key)
    if r.key == "whisper_device" and value == "cuda":
        return "auto"  # GPU only → Accurate
    if r.key == "response_speed" and value not in SPEED_PRESETS:
        wait = float(values.get("vad_stop_secs", 0.5))
        return min(SPEED_PRESETS, key=lambda n: abs(SPEED_PRESETS[n]["vad_stop_secs"] - wait))
    return value
