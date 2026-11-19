"""Where local models live: ~/.local/share/omarum/models (spec §6.2)."""

from __future__ import annotations

from pathlib import Path

from omarum.paths import DATA_DIR

MODELS_DIR = DATA_DIR / "models"


def resolve_whisper_model(name: str, models_dir: Path = MODELS_DIR) -> str:
    """A downloaded model folder if we have one, else the name (faster-whisper downloads it)."""
    local = models_dir / "whisper" / name
    return str(local) if (local / "model.bin").is_file() else name


def pick_whisper(cfg, cuda_devices: int | None = None) -> tuple[str, str, str]:
    """(model, device, compute_type): the big model on a GPU, a small one on the CPU."""
    if cuda_devices is None:
        import ctranslate2

        cuda_devices = ctranslate2.get_cuda_device_count()
    use_cuda = cfg.whisper_device == "cuda" or (cfg.whisper_device == "auto" and cuda_devices > 0)
    if use_cuda:
        return (cfg.whisper_model, "cuda", "default")
    return (cfg.whisper_cpu_model, "cpu", "int8")
