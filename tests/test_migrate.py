import json
from pathlib import Path

from omarum import migrate, setup


def old_install(home: Path, repo: Path) -> None:
    """What phase 5 left behind."""
    cfg = home / ".config"
    (cfg / "systemd/user").mkdir(parents=True)
    for u in ("omarum.service", "omarum-orb.service"):
        (cfg / "systemd/user" / u).write_text("[Unit]\nDescription=Omarum voice companion (Rum)\n")
    (cfg / "hypr").mkdir()
    (cfg / "hypr/omarum.lua").write_text("-- Written by Omarum (change these in `omarum settings`, not here).\n")
    (cfg / "hypr/bindings.lua").write_text('o.bind("A", "a", "a")\n\n-- Omarum voice companion\npcall(require, "hypr.omarum")\n')
    (cfg / "omarchy/extensions").mkdir(parents=True)
    (cfg / "omarchy/extensions/omarchy-menu.jsonc").write_text(
        '{\n  "omarum": {"icon":"x","label":"Omarum"},\n  "omarum.talk": {"icon":"x","label":"Talk","action":"omarum tap"},\n  "mine": {"label":"Mine"}\n}\n')
    (cfg / "omarchy/hooks/theme-set.d").mkdir(parents=True)
    (cfg / "omarchy/hooks/theme-set.d/50-omarum").write_text("#!/bin/sh\n# Added by Omarum: refresh the orb\n")
    (cfg / "omarchy/hooks/theme-set.d/10-mine").write_text("#!/bin/sh\necho mine\n")
    (cfg / "omarchy/plugins").mkdir(parents=True)
    (cfg / "omarchy/plugins/omarum").symlink_to(repo)
    apps = home / ".local/share/applications"
    apps.mkdir(parents=True)
    (apps / "omarum.desktop").write_text("[Desktop Entry]\nName=Omarum\nExec=omarum settings\n")
    (home / ".local/share/uv/tools/omarum").mkdir(parents=True)


def test_migrate_removes_only_what_omarum_added(tmp_path):
    home, repo = tmp_path / "home", tmp_path / "repo"
    repo.mkdir()
    old_install(home, repo)
    ran = []

    def fake_run(cmd):
        ran.append(cmd)
        if cmd[:3] == ["uv", "tool", "uninstall"]:  # like the real one: the tool folder goes
            import shutil
            shutil.rmtree(home / ".local/share/uv/tools/omarum")

    done = migrate.run(home, run=fake_run)
    cfg = home / ".config"
    assert not (cfg / "systemd/user/omarum.service").exists()
    assert not (cfg / "systemd/user/omarum-orb.service").exists()
    assert ["systemctl", "--user", "disable", "--now", "omarum-orb.service", "omarum.service"] in ran
    assert not (cfg / "hypr/omarum.lua").exists()
    assert (cfg / "hypr/bindings.lua").read_text() == 'o.bind("A", "a", "a")\n'
    menu = (cfg / "omarchy/extensions/omarchy-menu.jsonc").read_text()
    assert "omarum" not in menu and '"mine"' in menu
    assert not (cfg / "omarchy/hooks/theme-set.d/50-omarum").exists()
    assert (cfg / "omarchy/hooks/theme-set.d/10-mine").exists()
    assert not (cfg / "omarchy/plugins/omarum").is_symlink()
    assert not (home / ".local/share/applications/omarum.desktop").exists()
    assert ["uv", "tool", "uninstall", "omarum"] in ran
    assert len(done) >= 7
    # Second run: nothing left to do.
    ran.clear()
    assert migrate.run(home, run=lambda cmd: ran.append(cmd)) == [] and ran == []


def test_migrate_leaves_lookalikes_alone(tmp_path):
    home = tmp_path / "home"
    (home / ".config/hypr").mkdir(parents=True)
    (home / ".config/hypr/omarum.lua").write_text("-- my own file\n")
    (home / ".local/share/applications").mkdir(parents=True)
    (home / ".local/share/applications/omarum.desktop").write_text("[Desktop Entry]\nExec=something-else\n")
    assert migrate.run(home, run=lambda cmd: None) == []
    assert (home / ".config/hypr/omarum.lua").exists()


def test_setup_reports_progress_and_skips_present_models(tmp_path, capsys):
    models = tmp_path / "models"
    got = []
    setup.run(models, download_whisper=lambda name, dest: got.append(("whisper", name)) or
              (dest.mkdir(parents=True), (dest / "model.bin").write_bytes(b"x")),
              download_file=lambda url, dest: got.append(("file", dest.name)) or dest.write_bytes(b"x"),
              migrate_fn=lambda: ["removed old service"], gpu=False)
    lines = [json.loads(l) for l in capsys.readouterr().out.splitlines()]
    assert lines[-1]["step"] == "ready"
    assert all({"step", "done", "total", "message"} <= set(l) for l in lines)
    assert ("whisper", "base.en") in got and ("file", "kokoro-v1.0.onnx") in got
    got.clear()
    setup.run(models, download_whisper=lambda n, d: got.append(n), download_file=lambda u, d: got.append(d),
              migrate_fn=lambda: [], gpu=False)
    assert got == []  # everything already there
