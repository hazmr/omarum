"""Where local models live: ~/.local/share/omarum/models (spec §6.2)."""

from __future__ import annotations

from pathlib import Path

from omarum.paths import DATA_DIR

MODELS_DIR = DATA_DIR / "models"


def resolve_whisper_model(name: str, models_dir: Path = MODELS_DIR) -> str:
    """A downloaded model folder if we have one, else the name (faster-whisper downloads it)."""
    local = models_dir / "whisper" / name
    return str(local) if (local / "model.bin").is_file() else name


CUDA_LIBS = ("libcublas.so.12",)  # what CTranslate2's CUDA build loads to transcribe


def cuda_libs_loadable(loader=None) -> bool:
    """A GPU is only usable for Whisper if the CUDA math libraries load (the driver alone isn't enough)."""
    import ctypes

    load = loader or ctypes.CDLL
    try:
        for name in CUDA_LIBS:
            load(name)
    except OSError:
        return False
    return True


def pick_whisper(cfg, cuda_devices: int | None = None, cuda_libs: bool | None = None) -> tuple[str, str, str]:
    """(model, device, compute_type): the big model on a working GPU, a small one on the CPU."""
    if cuda_devices is None:
        import ctranslate2

        cuda_devices = ctranslate2.get_cuda_device_count()
    if cuda_libs is None:
        cuda_libs = cuda_libs_loadable() if cuda_devices > 0 else False
    gpu = cuda_devices > 0 and cuda_libs
    use_cuda = (cfg.whisper_device == "cuda" and gpu) or (cfg.whisper_device == "auto" and gpu)
    if use_cuda:
        return (cfg.whisper_model, "cuda", "default")
    if cfg.whisper_device == "cuda" and cuda_devices > 0 and not cuda_libs:
        from loguru import logger

        logger.warning("whisper_device = cuda, but libcublas.so.12 isn't installed; using the CPU model")
    return (cfg.whisper_cpu_model, "cpu", "int8")


def make_stt(cfg, factory, cuda_devices: int | None = None, cuda_libs: bool | None = None):
    """Build the speech-to-text service; a GPU too full for Whisper falls back to the CPU model.

    `factory(model, device, compute_type)` builds the service (it loads the model).
    """
    model, device, compute = pick_whisper(cfg, cuda_devices, cuda_libs)
    try:
        return factory(model, device, compute)
    except RuntimeError as exc:
        msg = str(exc).lower()
        if device != "cuda" or not ("out of memory" in msg or "cuda" in msg):
            raise
        from loguru import logger

        logger.warning(f"whisper {model} doesn't fit on the GPU ({exc}); using {cfg.whisper_cpu_model} on the CPU")
        return factory(cfg.whisper_cpu_model, "cpu", "int8")


_WHISPER_CACHE: dict = {}


def cached_whisper_model(name: str, device: str, compute: str, loader=None):
    """The faster-whisper model, loaded once and kept for every conversation (saves ~0.5 s per start)."""
    key = (name, device, compute)
    if key not in _WHISPER_CACHE:
        if loader is None:
            from faster_whisper import WhisperModel as loader
        _WHISPER_CACHE[key] = loader(name, device=device, compute_type=compute)
    return _WHISPER_CACHE[key]
