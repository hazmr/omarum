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

    assert pick_whisper(Config(), cuda_devices=1, cuda_libs=True) == ("large-v3-turbo", "cuda", "default")


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
    assert calls == [("large-v3-turbo", "cuda", "default"), ("base.en", "cpu", "int8")]


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
    assert pick_whisper(Config(), cuda_devices=1, cuda_libs=True) == ("large-v3-turbo", "cuda", "default")


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
