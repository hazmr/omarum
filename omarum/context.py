"""What Rum knows when a conversation starts (spec §6.2)."""

from __future__ import annotations

from datetime import date, datetime

from omarum import persona
from omarum.config import Config

RECENT_JOURNALS = 3


def _read(path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _recent_journals(store, limit: int = RECENT_JOURNALS) -> list[tuple[date, str]]:
    entries = []
    if store.journal_dir.is_dir():
        for f in store.journal_dir.glob("*.md"):
            try:
                entries.append((date.fromisoformat(f.stem), _read(f)))
            except ValueError:
                continue
    entries = [e for e in sorted(entries) if e[1]]
    return entries[-limit:]


def build_system_prompt(cfg: Config, store, now: datetime) -> str:
    sections = [persona.load(cfg, store).strip()]
    profile = _read(store.profile_path)
    if profile:
        sections.append(f"## What you know about {cfg.user_name}\n{profile}")
    journals = _recent_journals(store)
    if journals:
        body = "\n\n".join(f"### {d.isoformat()}\n{text}" for d, text in journals)
        sections.append(f"## Recent days\n{body}")
    sections.append(f"## Right now\nIt is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y, %H:%M')}.")
    return "\n\n".join(sections) + "\n"
