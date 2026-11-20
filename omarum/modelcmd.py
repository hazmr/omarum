"""`omarum models list [--json] | download ID | cancel ID | remove ID`.

The settings window runs `download` as a child process and reads its JSON progress lines;
`cancel` stops a running download (its partial file stays, so the next download resumes).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import sys
from pathlib import Path

from omarum import catalog, downloader

VOICE_MODELS = {"kokoro": "kokoro", "piper": "piper-amy"}


def in_use(cfg) -> set[str]:
    """Models Rum needs with these settings: never removed from the window."""
    used = {"whisper-base"}
    if cfg.whisper_device in ("auto", "cuda"):
        used |= {"whisper-large-turbo", "gpu"}
    elif cfg.whisper_cpu_model == "small.en":
        used.add("whisper-small")
    if cfg.voice_primary in VOICE_MODELS:
        used.add(VOICE_MODELS[cfg.voice_primary])
    return used


def _list(models_dir: Path, cfg, as_json: bool) -> int:
    used = in_use(cfg)
    rows = [{**catalog.state(m, models_dir), "size": m.approx_bytes, "in_use": m.id in used,
             "removable": m.removable} for m in catalog.CATALOG]
    if as_json:
        print(json.dumps(rows), flush=True)
    else:
        for r in rows:
            print(f"{r['id']:22} {r['state']:12} {r['done']}/{r['total']}")
    return 0


def _download(m: catalog.Model, models_dir: Path) -> int:
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))

    def emit(event: dict) -> None:
        print(json.dumps(event), flush=True)

    try:
        if m.resolver == "pypi-wheels":
            from omarum import gpupack

            files = gpupack.wheel_files()
            downloader.download(m, models_dir, files, emit, lambda: stop["now"])
            folder = Path(models_dir) / m.folder
            for f in files:
                if (folder / f.path).is_file():
                    gpupack.unpack(folder / f.path, folder)
        else:
            downloader.download(m, models_dir, list(m.files), emit, lambda: stop["now"])
    except downloader.Cancelled:
        return 2
    except Exception as exc:  # recorded by downloader.download; say it here too
        print(f"{m.title}: {exc}", file=sys.stderr)
        return 1
    return 0


def _cancel(m: catalog.Model, models_dir: Path) -> int:
    p = catalog.state_path(m, models_dir)
    try:
        pid = int(json.loads(p.read_text()).get("pid") or 0)
    except (OSError, ValueError):
        return 0
    if pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return 0


def _remove(m: catalog.Model, models_dir: Path, cfg) -> int:
    if not m.removable:
        print(f"{m.title} is always kept (Rum falls back to it)", file=sys.stderr)
        return 1
    if m.id in in_use(cfg):
        print(f"{m.title} is in use; choose another setting first", file=sys.stderr)
        return 1
    folder = Path(models_dir) / m.folder
    if m.resolver:
        shutil.rmtree(folder, ignore_errors=True)
    else:
        for f in m.files:
            (folder / f.path).unlink(missing_ok=True)
            (folder / (f.path + ".part")).unlink(missing_ok=True)
    catalog.clear_state(m, models_dir)
    return 0


def main(argv: list[str], models_dir: Path | None = None, cfg=None) -> int:
    if models_dir is None:
        from omarum.models import MODELS_DIR

        models_dir = MODELS_DIR
    if cfg is None:
        from omarum.config import load_config

        cfg = load_config()
    if not argv:
        print("usage: omarum models list [--json] | download ID | cancel ID | remove ID", file=sys.stderr)
        return 1
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        return _list(models_dir, cfg, "--json" in rest)
    if cmd not in ("download", "cancel", "remove") or not rest:
        print(f"unknown: models {' '.join(argv)}", file=sys.stderr)
        return 1
    try:
        m = catalog.by_id(rest[0])
    except KeyError:
        print(f"no model called {rest[0]!r}", file=sys.stderr)
        return 1
    if cmd == "download":
        return _download(m, models_dir)
    if cmd == "cancel":
        return _cancel(m, models_dir)
    return _remove(m, models_dir, cfg)
