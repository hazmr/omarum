import json
import os
import signal

from omarum import catalog, modelcmd
from omarum.config import Config


def test_list_reports_running_download(tmp_path, capsys):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, done=10, total=100)
    assert modelcmd.main(["list", "--json"], models_dir=tmp_path, cfg=Config()) == 0
    rows = {r["id"]: r for r in json.loads(capsys.readouterr().out)}
    assert rows["kokoro"]["state"] == "downloading" and rows["kokoro"]["done"] == 10
    assert rows["whisper-large-turbo"]["size"] == catalog.by_id("whisper-large-turbo").approx_bytes
    assert set(rows) == {m.id for m in catalog.CATALOG}


def test_in_use_follows_processing_and_voice():
    accurate = modelcmd.in_use(Config(whisper_device="auto", voice_primary="kokoro"))
    assert {"whisper-base", "whisper-large-turbo", "gpu", "kokoro"} <= accurate
    fast = modelcmd.in_use(Config(whisper_device="cpu", voice_primary="piper"))
    assert "whisper-large-turbo" not in fast and "gpu" not in fast and "piper-amy" in fast


def test_remove_refuses_in_use_and_base(tmp_path, capsys):
    cfg = Config(whisper_device="auto")
    assert modelcmd.main(["remove", "whisper-base"], models_dir=tmp_path, cfg=cfg) == 1
    assert modelcmd.main(["remove", "whisper-large-turbo"], models_dir=tmp_path, cfg=cfg) == 1
    assert "in use" in capsys.readouterr().err


def test_remove_deletes_files(tmp_path):
    m = catalog.by_id("piper-amy")
    d = tmp_path / "piper"
    d.mkdir()
    for f in m.files:
        (d / f.path).write_bytes(b"x")
    (d / "en_US-amy-medium.onnx.part").write_bytes(b"x")
    assert modelcmd.main(["remove", "piper-amy"], models_dir=tmp_path, cfg=Config(voice_primary="kokoro")) == 0
    assert catalog.state(m, tmp_path)["state"] == "missing"


def test_remove_gpu_deletes_the_folder(tmp_path):
    gpu = tmp_path / "gpu"
    gpu.mkdir()
    (gpu / "libcublas.so.12").write_bytes(b"x")
    assert modelcmd.main(["remove", "gpu"], models_dir=tmp_path, cfg=Config(whisper_device="cpu")) == 0
    assert not gpu.exists()


def test_cancel_signals_the_downloader(tmp_path, monkeypatch):
    m = catalog.by_id("kokoro")
    catalog.write_state(m, tmp_path, done=1, total=2)
    sent = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append(sig))
    assert modelcmd.main(["cancel", "kokoro"], models_dir=tmp_path, cfg=Config()) == 0
    assert signal.SIGTERM in sent


def test_download_prints_progress_and_exit_codes(tmp_path, capsys, monkeypatch):
    def fake_download(m, models_dir, files, emit, cancelled):
        emit({"id": m.id, "state": "downloading", "done": 1, "total": 2})
        emit({"id": m.id, "state": "ready", "done": 2, "total": 2})

    monkeypatch.setattr(modelcmd.downloader, "download", fake_download)
    assert modelcmd.main(["download", "piper-amy"], models_dir=tmp_path, cfg=Config()) == 0
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert lines[-1]["state"] == "ready"


def test_unknown_model_is_an_error(tmp_path, capsys):
    assert modelcmd.main(["download", "nope"], models_dir=tmp_path, cfg=Config()) == 1


def test_cli_routes_models(monkeypatch):
    import pytest

    from omarum import cli

    got = []
    monkeypatch.setattr(modelcmd, "main", lambda argv: got.append(argv) or 0)
    with pytest.raises(SystemExit) as e:
        cli.main(["models", "download", "gpu"])
    assert got == [["download", "gpu"]] and e.value.code == 0


def test_setup_downloads_whisper_through_the_catalog(tmp_path, monkeypatch):
    from omarum import setup

    got = []
    monkeypatch.setattr(setup.downloader, "download",
                        lambda m, models_dir, files, emit, cancelled: got.append((m.id, [f.path for f in files])))
    setup._download_whisper("base.en", tmp_path / "whisper" / "base.en")
    assert got[0][0] == "whisper-base" and "model.bin" in got[0][1]


def test_in_use_with_zonos3_and_accurate_is_whisper_small():
    used = modelcmd.in_use(Config(whisper_device="auto", voice_primary="zonos3"))
    assert "whisper-small" in used and "whisper-large-turbo" not in used and "gpu" not in used
