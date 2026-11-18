"""Omarum settings, loaded from ~/.config/omarum/config.toml."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarum" / "config.toml"


def _default_user() -> str:
    return os.environ.get("USER", "friend").capitalize()


@dataclass
class Config:
    companion_name: str = "Rum"
    user_name: str = field(default_factory=_default_user)
    brain_model: str = "haiku"
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # auto | cuda | cpu
    whisper_cpu_model: str = "base.en"
    voice_primary: str = "elevenlabs"  # elevenlabs | kokoro | piper (cloud falls back to kokoro)
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # premade "Rachel"; change in config.toml
    elevenlabs_model: str = "eleven_flash_v2_5"
    kokoro_voice: str = "af_heart"
    piper_voice: str = "en_US-amy-medium"
    vad_stop_secs: float = 0.6
    vad_confidence: float = 0.8
    vad_start_secs: float = 0.3
    vad_min_volume: float = 0.7
    interrupt_min_words: int = 3
    mute_while_speaking: bool = True  # stops Rum hearing itself without echo cancellation
    whisper_no_speech_prob: float = 0.3
    idle_timeout_secs: float = 8.0
    orb_position: str = "top-right"


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        data = {}
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known})
