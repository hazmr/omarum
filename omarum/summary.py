"""What the bar panel shows, as one JSON object (`omarum summary`). Stdlib only."""

from __future__ import annotations

from datetime import date, timedelta

from omarum import brains
from omarum.theme import RGB, vivid

VOICE_NAMES = {"elevenlabs": "ElevenLabs", "zonos3": "ZONOS3", "kokoro": "Kokoro", "piper": "Piper"}


def duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def ears_label(cfg, has_gpu: bool) -> str:
    gpu = cfg.whisper_device == "cuda" or (cfg.whisper_device == "auto" and has_gpu)
    return f"Whisper · {cfg.whisper_model if gpu else cfg.whisper_cpu_model}"


def voice_label(cfg) -> str:
    name = VOICE_NAMES.get(cfg.voice_primary, cfg.voice_primary)
    detail = {"zonos3": cfg.zonos3_voice, "kokoro": cfg.kokoro_voice}.get(cfg.voice_primary, "")
    return f"{name} · {detail}" if detail else name


def shortcut_label(shortcut: str) -> str:
    if not shortcut.strip():
        return "none"
    return "+".join(part.strip().capitalize() for part in shortcut.split("+"))


def to_hex(rgb: RGB) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def _when(day: date, time: str, today: date) -> str:
    if day == today:
        return f"today {time}"
    if day == today - timedelta(days=1):
        return f"yesterday {time}"
    return f"{day.strftime('%b')} {day.day} {time}"


def summary(cfg, talks, today: date, has_gpu: bool, palette: dict[str, RGB]) -> dict:
    last = talks[0] if talks else None
    return {
        "name": cfg.companion_name,
        "brain": brains.label(cfg),
        "ears": ears_label(cfg, has_gpu),
        "voice": voice_label(cfg),
        "shortcut": shortcut_label(cfg.talk_shortcut),
        "talks": len(talks),
        "talk_keys": cfg.talk_shortcut,  # what the plugin binds (Hyprland syntax)
        "orb": {"style": cfg.orb_style, "position": cfg.orb_position, "size": cfg.orb_size},
        "last": None if last is None else {
            "text": last.first_line, "when": _when(last.day, last.time, today), "length": duration(last.seconds)},
        # The orb's own colors (theme.state_color), so the bar icon matches the orb on screen.
        "colors": {
            "user": to_hex(vivid(palette["user"])),
            "companion": to_hex(vivid(palette["companion"])),
            "idle": to_hex(palette["idle"]),
            "error": to_hex(vivid(palette["error"])),
        },
    }


def current() -> dict:
    """The summary for this machine, right now."""
    import shutil
    import subprocess

    from omarum.config import load_config
    from omarum.library import talks
    from omarum.store import Store
    from omarum.theme import palette_for

    cfg = load_config()
    has_gpu = False
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=3).stdout
            from omarum.models import cuda_libs_loadable

            has_gpu = "GPU" in out and cuda_libs_loadable()
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        all_talks = talks(Store())
    except OSError:
        all_talks = []
    return summary(cfg, all_talks, date.today(), has_gpu, palette_for(cfg.orb_colors))
