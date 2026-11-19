"""What Rum knows when a conversation starts (spec §6.2)."""

from __future__ import annotations

from datetime import date, datetime

from omarum import persona
from omarum.config import Config

RECENT_JOURNALS = 3
EARLIER_TODAY_LINES = 40


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


def _earlier_today(cfg: Config, store, today: date, limit: int = EARLIER_TODAY_LINES) -> str:
    """Today's conversations straight from the transcripts: instant, before any memory pass runs."""
    from omarum.recorder import read_transcript

    names = {"user": cfg.user_name, "companion": cfg.companion_name}
    lines = [
        f"{names.get(r.get('who'), r.get('who'))}: {r['text']}"
        for d in store.conversations_on(today)
        for r in read_transcript(d / "transcript.jsonl")
    ]
    return "\n".join(lines[-limit:])


def build_system_prompt(cfg: Config, store, now: datetime) -> str:
    sections = [persona.load(cfg, store).strip()]
    profile = _read(store.profile_path)
    if profile:
        sections.append(f"## What you know about {cfg.user_name}\n{profile}")
    journals = _recent_journals(store)
    if journals:
        body = "\n\n".join(f"### {d.isoformat()}\n{text}" for d, text in journals)
        sections.append(f"## Recent days\n{body}")
    today = _earlier_today(cfg, store, now.date())
    if today:
        sections.append(f"## Earlier today\n{today}")
    from omarum import firstmeet

    if firstmeet.is_first_meeting(store):
        sections.append(firstmeet.prompt_section(cfg).strip())
    sections.append(f"## Right now\nIt is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y, %H:%M')}.")
    return "\n\n".join(sections) + "\n"
