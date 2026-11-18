from pathlib import Path

from omarum.config import load_config


def test_defaults_when_file_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("USER", "hazem")
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.companion_name == "Rum"
    assert cfg.user_name == "Hazem"
    assert cfg.brain_model == "haiku"
    assert cfg.vad_stop_secs == 0.6
    assert cfg.idle_timeout_secs == 8.0
    assert cfg.orb_position == "top-right"


def test_file_overrides(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('companion_name = "Noa"\n')
    cfg = load_config(p)
    assert cfg.companion_name == "Noa"
    assert cfg.idle_timeout_secs == 8.0


def test_unknown_keys_ignored(tmp_path: Path):
    p = tmp_path / "config.toml"
    p.write_text('bogus = 1\nvad_stop_secs = 0.8\n')
    cfg = load_config(p)
    assert cfg.vad_stop_secs == 0.8
    assert not hasattr(cfg, "bogus")
