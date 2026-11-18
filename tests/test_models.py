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

    assert pick_whisper(Config(), cuda_devices=1) == ("large-v3-turbo", "cuda", "default")


def test_pick_whisper_falls_back_to_cpu_model():
    from omarum.config import Config
    from omarum.models import pick_whisper

    assert pick_whisper(Config(), cuda_devices=0) == ("base.en", "cpu", "int8")


def test_pick_whisper_respects_forced_device():
    from omarum.config import Config
    from omarum.models import pick_whisper

    assert pick_whisper(Config(whisper_device="cpu"), cuda_devices=1) == ("base.en", "cpu", "int8")
