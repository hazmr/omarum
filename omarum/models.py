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


def make_stt(cfg, factory, cuda_devices: int | None = None):
    """Build the speech-to-text service; a GPU too full for Whisper falls back to the CPU model.

    `factory(model, device, compute_type)` builds the service (it loads the model).
    """
    model, device, compute = pick_whisper(cfg, cuda_devices)
    try:
        return factory(model, device, compute)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if device != "cuda" or not ("out of memory" in msg or "cuda" in msg):
            raise
        from loguru import logger

        logger.warning(f"whisper {model} doesn't fit on the GPU ({exc}); using {cfg.whisper_cpu_model} on the CPU")
        return factory(cfg.whisper_cpu_model, "cpu", "int8")
