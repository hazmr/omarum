import json
from pathlib import Path

from omarum import catalog


def test_missing_then_ready(tmp_path):
    m = catalog.by_id("piper-amy")
    assert catalog.state(m, tmp_path)["state"] == "missing"
    for f in m.files:
        p = tmp_path / m.folder / f.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    assert catalog.state(m, tmp_path)["state"] == "ready"


def test_partial_counts_part_bytes(tmp_path):
    m = catalog.by_id("kokoro")
    (tmp_path / "kokoro").mkdir()
    (tmp_path / "kokoro" / "kokoro-v1.0.onnx.part").write_bytes(b"x" * 10)
    s = catalog.state(m, tmp_path)
    assert s["state"] == "partial" and s["done"] == 10


def test_live_pid_is_downloading_dead_pid_is_not(tmp_path):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, done=5, total=9)  # our own pid: alive
    assert catalog.state(m, tmp_path)["state"] == "downloading"
    data = json.loads(catalog.state_path(m, tmp_path).read_text())
    data["pid"] = 2**22 + 7
    catalog.state_path(m, tmp_path).write_text(json.dumps(data))
    assert catalog.state(m, tmp_path)["state"] != "downloading"


def test_failed_keeps_the_reason(tmp_path):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, error="connection reset", pid=2**22 + 7)
    s = catalog.state(m, tmp_path)
    assert s["state"] == "failed" and s["error"] == "connection reset"


def test_gpu_ready_when_both_libraries_are_there(tmp_path):
    m = catalog.by_id("gpu")
    (tmp_path / "gpu").mkdir()
    (tmp_path / "gpu" / "libcublas.so.12").write_bytes(b"x")
    assert catalog.state(m, tmp_path)["state"] != "ready"
    (tmp_path / "gpu" / "libcudnn.so.9").write_bytes(b"x")
    assert catalog.state(m, tmp_path)["state"] == "ready"


def test_catalog_ids_and_base_not_removable():
    assert [m.id for m in catalog.CATALOG] == [
        "whisper-base", "whisper-small", "whisper-large-turbo", "gpu", "kokoro", "piper-amy"]
    assert catalog.by_id("whisper-base").removable is False


def test_whisper_files_match_the_downloaded_folders():
    base = catalog.by_id("whisper-base")
    assert [f.path for f in base.files] == ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
    assert base.files[1].url == "https://huggingface.co/Systran/faster-whisper-base.en/resolve/main/model.bin"
    turbo = catalog.by_id("whisper-large-turbo")
    assert "vocabulary.json" in [f.path for f in turbo.files]
    assert "mobiuslabsgmbh/faster-whisper-large-v3-turbo" in turbo.files[0].url


def test_catalog_is_stdlib_only():
    src = Path(catalog.__file__).read_text()
    assert "import requests" not in src and "huggingface_hub" not in src and "omarum.models" not in src
