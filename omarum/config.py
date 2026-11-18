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
    whisper_device: str = "cuda"
    piper_voice: str = "en_US-amy-medium"
    vad_stop_secs: float = 0.6
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
