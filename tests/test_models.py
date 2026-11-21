from pathlib import Path

from omarum.models import resolve_whisper_model


def test_uses_local_dir_when_present(tmp_path: Path):
    d = tmp_path / "whisper" / "large-v3-turbo"
    d.mkdir(parents=True)
    (d / "model.bin").write_bytes(b"x")
    assert resolve_whisper_model("large-v3-turbo", tmp_path) == str(d)


def test_falls_back_to_name(tmp_path: Path):
    assert resolve_whisper_model("small", tmp_path) == "small"


def test_pick_whisper_uses_gpu_model_when_cuda_available():
    from omarum.config import Config
    from omarum.models import pick_whisper

    assert pick_whisper(Config(), cuda_devices=1, cuda_libs=True) == ("large-v3-turbo", "cuda", "int8_float16")


def test_pick_whisper_falls_back_to_cpu_model():
    from omarum.config import Config
    from omarum.models import pick_whisper

    assert pick_whisper(Config(), cuda_devices=0) == ("base.en", "cpu", "int8")


def test_pick_whisper_respects_forced_device():
    from omarum.config import Config
    from omarum.models import pick_whisper

    assert pick_whisper(Config(whisper_device="cpu"), cuda_devices=1) == ("base.en", "cpu", "int8")


def test_make_stt_falls_back_to_cpu_on_cuda_oom():
    from omarum.config import Config
    from omarum.models import make_stt

    calls = []

    def factory(model, device, compute):
        calls.append((model, device, compute))
        if device == "cuda":
            raise RuntimeError("CUDA failed with error out of memory")
        return "stt"

    assert make_stt(Config(), factory, cuda_devices=1, cuda_libs=True) == "stt"
    assert calls == [("large-v3-turbo", "cuda", "int8_float16"), ("base.en", "cpu", "int8")]


def test_make_stt_reraises_other_errors():
    import pytest

    from omarum.config import Config
    from omarum.models import make_stt

    def factory(model, device, compute):
        raise RuntimeError("model file is corrupt")

    with pytest.raises(RuntimeError, match="corrupt"):
        make_stt(Config(), factory, cuda_devices=1, cuda_libs=True)


def test_make_stt_cpu_errors_are_not_retried():
    import pytest

    from omarum.config import Config
    from omarum.models import make_stt

    calls = []

    def factory(model, device, compute):
        calls.append(device)
        raise RuntimeError("out of memory")

    with pytest.raises(RuntimeError):
        make_stt(Config(), factory, cuda_devices=0)
    assert calls == ["cpu"]


def test_pick_whisper_needs_cuda_libraries_not_just_a_gpu():
    from omarum.config import Config
    from omarum.models import pick_whisper

    # A GPU the driver sees, but no libcublas: transcription would fail on every turn.
    assert pick_whisper(Config(), cuda_devices=1, cuda_libs=False) == ("base.en", "cpu", "int8")
    assert pick_whisper(Config(), cuda_devices=1, cuda_libs=True) == ("large-v3-turbo", "cuda", "int8_float16")


def test_cuda_libs_loadable_probe():
    from omarum.models import cuda_libs_loadable

    assert cuda_libs_loadable(loader=lambda name: object()) is True

    def missing(name):
        raise OSError(f"{name}: cannot open shared object file")

    assert cuda_libs_loadable(loader=missing) is False


def test_whisper_model_is_loaded_once_and_kept(monkeypatch):
    from omarum import models

    loads = []

    class FakeWhisperModel:
        def __init__(self, name, device, compute_type):
            loads.append((name, device))

    monkeypatch.setattr(models, "_WHISPER_CACHE", {})
    first = models.cached_whisper_model("base.en", "cpu", "int8", loader=FakeWhisperModel)
    again = models.cached_whisper_model("base.en", "cpu", "int8", loader=FakeWhisperModel)
    assert first is again and loads == [("base.en", "cpu")]
    models.cached_whisper_model("tiny.en", "cpu", "int8", loader=FakeWhisperModel)
    assert len(loads) == 2


def test_preload_loads_the_model_rum_will_use(monkeypatch):
    from omarum import models
    from omarum.config import Config

    got = []
    monkeypatch.setattr(models, "cached_whisper_model", lambda name, device, compute: got.append((name, device, compute)))
    models.preload_whisper(Config(), cuda_devices=0, cuda_libs=False)
    assert got == [(models.resolve_whisper_model("base.en"), "cpu", "int8")]


def test_preload_gpu_libs_loads_lt_first(tmp_path):
    from pathlib import Path

    from omarum import models

    gpu = tmp_path / "gpu"
    gpu.mkdir()
    for n in ("libcublas.so.12", "libcublasLt.so.12"):
        (gpu / n).write_bytes(b"")
    loaded = []
    assert models.preload_gpu_libs(tmp_path, loader=lambda p, mode=0: loaded.append(Path(p).name))
    assert loaded == ["libcublasLt.so.12", "libcublas.so.12"]


def test_preload_gpu_libs_without_the_pack(tmp_path):
    from omarum import models

    assert models.preload_gpu_libs(tmp_path, loader=lambda p, mode=0: None) is False


def test_pick_whisper_falls_back_when_gpu_pack_missing():
    from omarum import models
    from omarum.config import Config

    cfg = Config(whisper_device="auto")
    assert models.pick_whisper(cfg, cuda_devices=1, cuda_libs=False) == ("base.en", "cpu", "int8")
    assert models.pick_whisper(cfg, cuda_devices=1, cuda_libs=True)[1] == "cuda"


def test_noise_filter_is_rnnoise():
    from omarum.pipeline import noise_filter

    f = noise_filter()
    assert type(f).__name__ == "RNNoiseFilter"


async def test_gpu_out_of_memory_falls_back_to_the_cpu_model(monkeypatch):
    """Seen 2026-11-21 14:34: Superwhisper filled the GPU and Rum's transcription failed."""
    import numpy as np

    from omarum import pipeline
    from pipecat.frames.frames import TranscriptionFrame

    class Seg:
        text, no_speech_prob = "hello there", 0.0

    class OOM:
        supported_languages = None

        def transcribe(self, *a, **k):
            raise RuntimeError("CUDA failed with error out of memory")

    class CPU:
        supported_languages = None

        def transcribe(self, *a, **k):
            return iter([Seg()]), None

    loads = []
    monkeypatch.setattr(pipeline, "cached_whisper_model",
                        lambda name, device, compute: loads.append((name, device)) or (OOM() if device == "cuda" else CPU()))
    stt = pipeline.KeptWhisper(settings=pipeline.WhisperSTTService.Settings(model="large-v3-turbo"),
                               device="cuda", compute_type="int8_float16", fallback_model="base.en")
    frames = [f async for f in stt.run_stt(np.zeros(16000, np.int16).tobytes())]
    assert any(isinstance(f, TranscriptionFrame) and "hello there" in f.text for f in frames)
    assert loads[-1] == ("base.en", "cpu") and stt._device == "cpu"
