"""Downloads that resume, verify, and never leave a half model. Stdlib only.

A file downloads into `<name>.part`; an interrupted or cancelled download keeps it, and the
next try asks the server for the rest (HTTP Range). Only a complete file whose size (and sha256,
when known) is right gets its real name, so Rum can never load a broken model.
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
from pathlib import Path
from typing import Callable

from omarum import catalog
from omarum.catalog import FileSpec, Model

USER_AGENT = "omarum-downloader"


class Cancelled(Exception):
    pass


def _part(dest: Path) -> Path:
    return dest.with_name(dest.name + ".part")


def fetch(spec: FileSpec, dest: Path, on_bytes: Callable[[int], None], cancelled: Callable[[], bool],
          opener=urllib.request.urlopen, chunk: int = 1 << 20) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = _part(dest)
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(spec.url, headers={"User-Agent": USER_AGENT})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with opener(req, timeout=60) as resp:
        status = getattr(resp, "status", 200)
        length = int(resp.headers.get("Content-Length") or 0)
        if have and status != 206:  # the server ignored Range: start over, never append
            have = 0
        expected = spec.size or (have + length if length else 0)
        with open(part, "ab" if have else "wb") as out:
            if have:
                on_bytes(have)
            while True:
                if cancelled():
                    raise Cancelled(spec.path)
                data = resp.read(chunk)
                if not data:
                    break
                out.write(data)
                on_bytes(len(data))
    size = part.stat().st_size
    if expected and size < expected:
        raise ConnectionError(f"connection closed at {size} of {expected} bytes")
    if (expected and size != expected) or (spec.sha256 and _sha256(part) != spec.sha256):
        part.unlink(missing_ok=True)
        raise ValueError(f"{spec.path}: size/sha256 mismatch")
    part.replace(dest)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def _size(spec: FileSpec, opener) -> int:
    if spec.size:
        return spec.size
    try:
        req = urllib.request.Request(spec.url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with opener(req, timeout=30) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except OSError:
        return 0


def download(m: Model, models_dir: Path, files: list[FileSpec], emit: Callable[[dict], None],
             cancelled: Callable[[], bool], opener=urllib.request.urlopen) -> None:
    """Fetch every missing file of `m`, reporting {"id", "state", "done", "total"} as it goes."""
    folder = Path(models_dir) / m.folder
    todo = [f for f in files if not ((folder / f.path).is_file() and (folder / f.path).stat().st_size > 0)]
    sizes = [_size(f, opener) for f in todo]
    total = sum(sizes) or m.approx_bytes
    done = 0
    last = 0.0

    def report(force: bool = False) -> None:
        nonlocal last
        now = time.monotonic()
        if force or now - last >= 0.25:
            last = now
            catalog.write_state(m, models_dir, done=done, total=total)
            emit({"id": m.id, "state": "downloading", "done": done, "total": total})

    try:
        report(force=True)
        for f, size in zip(todo, sizes):
            spec = f if f.size or not size else FileSpec(f.url, f.path, size, f.sha256)
            base = done

            def on_bytes(n: int, base=base) -> None:
                nonlocal done
                done += n
                report()

            fetch(spec, folder / f.path, on_bytes, cancelled, opener=opener)
            done = base + (spec.size or (folder / f.path).stat().st_size)
        report(force=True)
    except Cancelled:
        catalog.clear_state(m, models_dir)
        emit({"id": m.id, "state": "partial", "done": done, "total": total})
        raise
    except Exception as exc:
        catalog.write_state(m, models_dir, done=done, total=total, error=str(exc)[:160], pid=0)
        emit({"id": m.id, "state": "failed", "done": done, "total": total, "error": str(exc)[:160]})
        raise
    catalog.clear_state(m, models_dir)
    emit({"id": m.id, "state": "ready", "done": total, "total": total})
