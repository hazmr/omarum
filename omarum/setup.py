"""First-load setup, run by the plugin: models, then the one-time migration.

`python -m omarum.setup` prints one JSON line per step: {"step", "done", "total", "message"};
the plugin's panel shows them. Safe to run again: present models are skipped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from omarum import catalog, downloader
from omarum.catalog import KOKORO_URL
KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


def _say(step: str, done: int, total: int, message: str) -> None:
    print(json.dumps({"step": step, "done": done, "total": total, "message": message}), flush=True)


WHISPER_IDS = {"base.en": "whisper-base", "small.en": "whisper-small", "large-v3-turbo": "whisper-large-turbo"}


def _download_whisper(name: str, dest: Path) -> None:
    """Through the catalog, like settings → Models: resumable, verified, never half there."""
    m = catalog.by_id(WHISPER_IDS[name])
    models_dir = Path(dest).parents[len(Path(m.folder).parts) - 1]
    downloader.download(m, models_dir, list(m.files), emit=lambda e: None, cancelled=lambda: False)


def _download_file(url: str, dest: Path) -> None:
    downloader.fetch(catalog.FileSpec(url, dest.name), dest, on_bytes=lambda n: None, cancelled=lambda: False)


def _migrate() -> list[str]:
    from omarum import migrate

    return migrate.run()


def run(models: Path, download_whisper=_download_whisper, download_file=_download_file,
        migrate_fn=_migrate, gpu: bool | None = None) -> None:
    if gpu is None:
        from omarum.models import cuda_libs_loadable

        gpu = cuda_libs_loadable()
    whisper = ["base.en"] + (["large-v3-turbo"] if gpu else [])
    steps = [("whisper", w) for w in whisper] + [("kokoro", f) for f in KOKORO_FILES]
    total = len(steps) + 1
    for i, (kind, name) in enumerate(steps):
        if kind == "whisper":
            dest = models / "whisper" / name
            if not (dest / "model.bin").is_file():
                _say("models", i, total, f"Downloading the {name} speech model")
                download_whisper(name, dest)
        else:
            dest = models / "kokoro" / name
            if not (dest.is_file() and dest.stat().st_size > 0):
                _say("models", i, total, f"Downloading the Kokoro voice ({name})")
                dest.parent.mkdir(parents=True, exist_ok=True)
                download_file(f"{KOKORO_URL}/{name}", dest)
    _say("migrate", total - 1, total, "Tidying up the old install")
    for line in migrate_fn():
        _say("migrate", total - 1, total, line)
    _say("ready", total, total, "Ready")


if __name__ == "__main__":
    from omarum.models import MODELS_DIR

    try:
        run(MODELS_DIR)
    except Exception as exc:  # the panel shows it
        _say("error", 0, 1, str(exc)[:200])
        sys.exit(1)
