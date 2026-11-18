"""Where local models live: ~/.local/share/omarum/models (spec §6.2)."""

from __future__ import annotations

from pathlib import Path

from omarum.claude_code_llm import DATA_DIR

MODELS_DIR = DATA_DIR / "models"


def resolve_whisper_model(name: str, models_dir: Path = MODELS_DIR) -> str:
    """A downloaded model folder if we have one, else the name (faster-whisper downloads it)."""
    local = models_dir / "whisper" / name
    return str(local) if (local / "model.bin").is_file() else name
