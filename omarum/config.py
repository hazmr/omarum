"""Omarum settings, loaded from ~/.config/omarum/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from omarum.brains import PROVIDERS

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarum" / "config.toml"


def _default_user() -> str:
    return os.environ.get("USER", "friend").capitalize()


@dataclass
class Config:
    companion_name: str = "Rum"
    user_name: str = field(default_factory=_default_user)
    brain: str = "claude-code"  # any provider in omarum/brains.py: a subscription CLI or an API
    brain_model: str = "haiku"  # any model name the provider accepts; "" = its default
    brain_url: str = ""  # only for brain = "custom": an OpenAI-compatible endpoint
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_cpu_model: str = "base.en"
    voice_primary: str = "elevenlabs"  # elevenlabs | zonos3 | kokoro | piper; falls back down that order
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # premade "Rachel"; change in config.toml
    elevenlabs_model: str = "eleven_flash_v2_5"
    zonos3_port: int = 1919
    zonos3_voice: str = "Savannah"  # a built-in voice name (Savannah, Willow, Imogen, Cillian...) or speaker id
    zonos3_language: str = "en_us"
    kokoro_voice: str = "af_heart"
    piper_voice: str = "en_US-amy-medium"
    voice_volume: int = 150  # percent; Rum's voice is raised before the speakers (clipped, never distorted by wrap)
    response_speed: str = "balanced"  # fast | balanced | patient: a preset for the two settings below
    vad_stop_secs: float = 0.5  # "Wait before answering": silence before Rum asks the smart-turn model if you're done
    vad_confidence: float = 0.8
    vad_start_secs: float = 0.3
    vad_min_volume: float = 0.7
    interrupt_min_words: int = 3
    mute_while_speaking: bool = True  # stops Rum hearing itself without echo cancellation
    whisper_no_speech_prob: float = 0.3
    whisper_ttfs_p99: float = 0.05  # turn already starts from a transcript; skip the STT safety wait
    idle_timeout_secs: float = 8.0
    record_audio: bool = True  # keep both voices of every conversation (spec §8)
    retention_days: int = 0  # 0 = keep conversations forever
    audio_release_secs: float = 0.6  # pause between sessions so the audio device is fully closed
    orb_position: str = "top-right"  # top-right | top-center | top-left | center | bottom-center
    orb_style: str = "glow"  # glow | lines | ring
    orb_size: int = 160  # px, 96-320
    orb_colors: str = "theme"  # theme | warm | glass | mono
    screen_look: bool = True  # "look at my screen": Rum takes one screenshot, only when you ask
    screen_awareness: bool = True  # Rum sees the file open in a focused code editor (IntelliJ, VS Code) when you talk
    talk_shortcut: str = "CTRL + SHIFT + SPACE"  # tap tap = open/close, hold = your turn, tap = stop Rum; "" = none
    settings_shortcut: str = ""  # opens the settings window; "" = none


CHOICES: dict[str, tuple] = {
    "brain": tuple(PROVIDERS),
    "response_speed": ("fast", "balanced", "patient", "custom"),
    "voice_primary": ("elevenlabs", "zonos3", "kokoro", "piper"),
    "orb_style": ("glow", "lines", "ring"),
    "orb_position": ("top-right", "top-center", "top-left", "center", "bottom-center"),
    "orb_colors": ("theme", "warm", "glass", "mono"),
    "whisper_device": ("auto", "cuda", "cpu"),
}


def _accept(name: str, value, default):
    """The value if it has the default's type (int ok for float) and an allowed choice, else None."""
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        value = float(value) if ok else value
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, str)
    if ok and name in CHOICES and value not in CHOICES[name]:
        ok = False
    return value if ok else None


def load_config(path: Path | None = None) -> Config:
    """Never raises on bad content: a wrong value falls back to its default (and is logged)."""
    import sys

    path = path or CONFIG_PATH
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        data = {}
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        print(f"omarum: {path}: {exc}; using defaults", file=sys.stderr)
        data = {}
    defaults = Config()
    values = {}
    for f in fields(Config):
        if f.name in data:
            v = _accept(f.name, data[f.name], getattr(defaults, f.name))
            if v is None:
                print(f"omarum: ignoring {f.name} = {data[f.name]!r} in {path}", file=sys.stderr)
            else:
                values[f.name] = v
    return Config(**values)
