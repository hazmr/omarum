"""What the settings window shows from Rum's memory and saved conversations. Stdlib only."""

from __future__ import annotations

import json
import shutil
import tarfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from omarum.transcripts import read_transcript


def facts(store) -> list[str]:
    try:
        lines = store.profile_path.read_text().splitlines()
    except OSError:
        return []
    return [l.strip()[2:] for l in lines if l.strip().startswith("- ")]


def forget(store, index: int) -> None:
    lines = store.profile_path.read_text().splitlines()
    fact_lines = [i for i, l in enumerate(lines) if l.strip().startswith("- ")]
    shutil.copyfile(store.profile_path, store.profile_path.with_suffix(".md.bak"))
    del lines[fact_lines[index]]
    store.profile_path.write_text("\n".join(lines) + ("\n" if lines else ""))


def journals(store) -> list[tuple[date, str]]:
    out = []
    for f in store.journal_dir.glob("*.md") if store.journal_dir.is_dir() else []:
        try:
            out.append((date.fromisoformat(f.stem), f.read_text().strip()))
        except ValueError:
            continue
    return sorted(out, reverse=True)


@dataclass
class Talk:
    dir: Path
    day: date
    time: str
    seconds: int | None
    first_line: str
    audio: list[Path]


def _seconds(meta_path: Path) -> int | None:
    try:
        meta = json.loads(meta_path.read_text())
        return int((datetime.fromisoformat(meta["ended"]) - datetime.fromisoformat(meta["started"])).total_seconds())
    except (OSError, ValueError, KeyError, TypeError):
        return None


def talks(store) -> list[Talk]:
    out = []
    for day in store._conversation_days():
        for d in store.conversations_on(day):
            rows = read_transcript(d / "transcript.jsonl")
            first = next((r["text"] for r in rows if r.get("who") == "user"), rows[0]["text"] if rows else "")
            if len(first) > 60:
                first = first[:59] + "…"
            audio = [p for name in ("user", "companion") for p in sorted(d.glob(f"{name}.*"))]
            out.append(Talk(d, day, f"{d.name[:2]}:{d.name[2:4]}", _seconds(d / "meta.json"), first, audio))
    return sorted(out, key=lambda t: (t.day, t.dir.name), reverse=True)


def play_command(talk: Talk) -> list[str]:
    if not talk.audio:
        return []
    return ["mpv", "--no-video", "--really-quiet", *map(str, talk.audio)]


def delete_talk(store, talk: Talk) -> None:
    root = store.conversations_dir.resolve()
    target = talk.dir.resolve()
    if root not in target.parents:
        raise ValueError(f"refusing to delete {target}: not a saved conversation")
    # Into the trash, not erased: <data>/trash/<day>/<conversation>. Restore by moving it back.
    trash = store.conversations_dir.parent / "trash" / target.parent.name
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / target.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(target), dest)


def export(store, dest: Path) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"omarum-export-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        tar.add(store.root, arcname="omarum")
    return out
