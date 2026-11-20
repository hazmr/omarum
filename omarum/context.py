"""What Rum knows when a conversation starts (spec §6.2)."""

from __future__ import annotations

from datetime import date, datetime

from omarum import persona
from omarum.config import Config

RECENT_JOURNALS = 3
LOOK_GUIDE = """\
## Looking at their screen
When they ask you to look ("look at my screen", "what do you see?"), a screenshot of their screen, taken right then, comes with what they say. Talk about it like a friend glancing over their shoulder: what matters for what they asked, in a sentence or two. Don't list everything on screen and never read long text aloud. If no screenshot came with it, say you couldn't see it this time.
"""

CODE_GUIDE = """\
## Code on their screen
When they're in a code editor, the file they have open comes with what they say, marked "On screen". Use it only when they talk about it ("what does this do?", "why is this here?").
Explaining code out loud, like a patient friend sitting next to them:
- Go in small pieces, because they're listening, not reading. First answer: only the big picture in plain words, three or four spoken sentences: what this file is for and why it exists. Then ask which part they want next, or offer the next one.
- When they want more, take one part at a time, by name ("the getAllCompanies method", "line 32"): what it does and how it connects, in three or four sentences. Translate jargon (a stream, an annotation, a mapper) into everyday words.
- Never read code or symbols aloud, no brackets, dots or arrows. Say what it does instead.
- Point out anything odd you notice, like commented-out code or a leftover joke, honestly and kindly.
- Never explain the whole file in one reply.
"""
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
    if getattr(cfg, "screen_awareness", False):
        sections.append(CODE_GUIDE.strip())
    if getattr(cfg, "screen_look", False):
        sections.append(LOOK_GUIDE.strip())
    sections.append("## Goodbyes\nWhen they say goodbye (\"bye\", \"good night\", \"that's all\"), answer with one short, warm goodbye line. The conversation closes right after you say it.")
    from omarum import firstmeet

    if firstmeet.is_first_meeting(store):
        sections.append(firstmeet.prompt_section(cfg).strip())
    sections.append(f"## Right now\nIt is {now.strftime('%A')}, {now.day} {now.strftime('%B %Y, %H:%M')}.")
    return "\n\n".join(sections) + "\n"
