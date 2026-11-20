"""Every model Rum can download, and what state each is in on disk. Stdlib only.

Used by the settings window (system Python) and by `omarum models` (the engine's venv).
A model's files live under `models_dir / folder`. While a download runs, a small state file
(`models_dir/.state/<id>.json`) holds its progress and pid, so any process can show it.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"


@dataclass(frozen=True)
class FileSpec:
    url: str
    path: str  # relative to the model's folder
    size: int = 0  # bytes, 0 = unknown until the server says
    sha256: str = ""


@dataclass(frozen=True)
class Model:
    id: str
    title: str
    group: str  # "Speech to text" | "Voices"
    folder: str  # relative to models_dir
    files: tuple[FileSpec, ...]
    approx_bytes: int
    removable: bool = True
    resolver: str = ""  # "pypi-wheels": files found at download time (GPU support)
    ready_files: tuple[str, ...] = ()  # what must exist when files aren't known ahead


def _hf(repo: str, names: tuple[str, ...]) -> tuple[FileSpec, ...]:
    return tuple(FileSpec(f"https://huggingface.co/{repo}/resolve/main/{n}", n) for n in names)


_WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")

CATALOG: tuple[Model, ...] = (
    Model("whisper-base", "Whisper Base", "Speech to text", "whisper/base.en",
          _hf("Systran/faster-whisper-base.en", _WHISPER_FILES), 145_000_000, removable=False),
    Model("whisper-small", "Whisper Small", "Speech to text", "whisper/small.en",
          _hf("Systran/faster-whisper-small.en", _WHISPER_FILES), 486_000_000),
    Model("whisper-large-turbo", "Whisper Large v3 Turbo", "Speech to text", "whisper/large-v3-turbo",
          _hf("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
              ("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json")),
          1_620_000_000),
    Model("gpu", "GPU support", "Speech to text", "gpu", (), 1_500_000_000,
          resolver="pypi-wheels", ready_files=("libcublas.so.12", "libcudnn.so.9")),
    Model("kokoro", "Kokoro", "Voices", "kokoro",
          tuple(FileSpec(f"{KOKORO_URL}/{n}", n) for n in ("kokoro-v1.0.onnx", "voices-v1.0.bin")), 337_000_000),
    Model("piper-amy", "Piper · Amy", "Voices", "piper",
          tuple(FileSpec(f"{PIPER_URL}/{n}", n) for n in ("en_US-amy-medium.onnx", "en_US-amy-medium.onnx.json")),
          63_000_000),
)


def by_id(model_id: str) -> Model:
    for m in CATALOG:
        if m.id == model_id:
            return m
    raise KeyError(model_id)


def state_path(m: Model, models_dir: Path) -> Path:
    return Path(models_dir) / ".state" / f"{m.id}.json"


def write_state(m: Model, models_dir: Path, **fields) -> None:
    """Record a download's progress (or failure) for any process to read. Atomic."""
    p = state_path(m, models_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"pid": os.getpid(), "at": time.time(), **fields}
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(p)


def clear_state(m: Model, models_dir: Path) -> None:
    state_path(m, models_dir).unlink(missing_ok=True)


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError):
        return False
    return True


def is_ready(m: Model, models_dir: Path) -> bool:
    folder = Path(models_dir) / m.folder
    names = m.ready_files or tuple(f.path for f in m.files)
    return all((folder / n).is_file() and (folder / n).stat().st_size > 0 for n in names)


def state(m: Model, models_dir: Path) -> dict:
    """{"id", "title", "group", "state", "done", "total", "error"}; state is
    ready | missing | partial | downloading | failed."""
    out = {"id": m.id, "title": m.title, "group": m.group, "state": "missing",
           "done": 0, "total": m.approx_bytes, "error": ""}
    folder = Path(models_dir) / m.folder
    saved = {}
    sp = state_path(m, models_dir)
    if sp.is_file():
        try:
            saved = json.loads(sp.read_text())
        except (OSError, ValueError):
            saved = {}
    if saved and not saved.get("error") and _alive(saved.get("pid")):
        out.update(state="downloading", done=int(saved.get("done", 0)),
                   total=int(saved.get("total") or m.approx_bytes))
        return out
    if is_ready(m, models_dir):
        out.update(state="ready", done=m.approx_bytes)
        return out
    if saved.get("error"):
        out.update(state="failed", error=str(saved["error"]))
    parts = list(folder.glob("*.part")) if folder.is_dir() else []
    if parts:
        out["done"] = sum(p.stat().st_size for p in parts)
        if out["state"] != "failed":
            out["state"] = "partial"
    return out
