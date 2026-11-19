"""After a conversation, Rum updates what it knows about the user; once a day it writes a journal.

Both passes run through the user's own isolated `claude` CLI. A failed or nonsensical pass
never touches the existing files: memory is only ever replaced by something valid.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import date
from typing import Callable

from loguru import logger

from omarum.claude_code_llm import DATA_DIR
from omarum.recorder import read_transcript

RunClaude = Callable[[str, str], str]
MAX_PROFILE_LINES = 200

PROFILE_SYSTEM = """\
You maintain {name}'s private notes about {user}, a person {name} talks with by voice every day.
You receive the current notes and the transcript of their latest conversation.
Return the COMPLETE updated notes and nothing else:
- one fact per line, each line starting with "- "
- add what's new and worth remembering (projects, people, plans, preferences, feelings, dates)
- update facts that changed and remove ones that are no longer true
- keep every existing line that is still true, word for word (the user may have written them)
- never record passwords, keys, card numbers or similar secrets
- no headings, no commentary, no blank preamble
If nothing new is worth keeping, return the current notes unchanged."""

JOURNAL_SYSTEM = """\
You are {name}, writing a short private journal entry about your day talking with {user}.
From the transcripts, write 3 to 8 plain sentences in your own warm voice: what you talked about,
how {user} seemed, and anything left unfinished that you want to ask about next time.
No headings, no lists, no markdown."""


class MemoryPassFailed(Exception):
    pass


def run_claude(system: str, prompt: str, model: str = "haiku", timeout: int = 120) -> str:
    """One-shot call to the user's logged-in claude CLI, isolated like Rum's brain."""
    if shutil.which("claude") is None:
        raise MemoryPassFailed("claude CLI not found")
    cmd = [
        "claude", "-p", "--output-format", "text", "--tools", "", "--no-session-persistence",
        "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands",
        "--model", model, "--system-prompt", system,
    ]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=DATA_DIR)
    except subprocess.TimeoutExpired as exc:
        raise MemoryPassFailed("claude timed out") from exc
    if result.returncode != 0:
        raise MemoryPassFailed((result.stderr or result.stdout).strip()[:200] or f"exit {result.returncode}")
    return result.stdout


def valid_profile(text: str) -> bool:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return 0 < len(lines) <= MAX_PROFILE_LINES and all(l.lstrip().startswith("- ") for l in lines)


def _dialogue(transcript: list[dict], cfg) -> str:
    names = {"user": cfg.user_name, "companion": cfg.companion_name}
    return "\n".join(f"{names.get(r.get('who'), r.get('who'))}: {r['text']}" for r in transcript)


def update_profile(store, transcript: list[dict], cfg, run: RunClaude = run_claude) -> bool:
    if not transcript:
        return False
    current = store.profile_path.read_text() if store.profile_path.exists() else ""
    system = PROFILE_SYSTEM.format(name=cfg.companion_name, user=cfg.user_name)
    prompt = f"CURRENT NOTES:\n{current.strip() or '(none yet)'}\n\nLATEST CONVERSATION:\n{_dialogue(transcript, cfg)}"
    try:
        new = run(system, prompt).strip()
    except Exception as exc:
        logger.warning(f"memory: profile update failed: {exc}")
        return False
    if not valid_profile(new):
        logger.warning(f"memory: rejected profile update: {new[:120]!r}")
        return False
    store.profile_path.parent.mkdir(parents=True, exist_ok=True)
    if store.profile_path.exists():
        shutil.copyfile(store.profile_path, store.profile_path.with_suffix(".md.bak"))
    store.profile_path.write_text(new + "\n")
    return True


def write_journal(store, day: date, cfg, run: RunClaude = run_claude) -> bool:
    path = store.journal_path(day)
    if path.exists():
        return False
    transcripts = [read_transcript(d / "transcript.jsonl") for d in store.conversations_on(day)]
    text = "\n\n---\n\n".join(_dialogue(t, cfg) for t in transcripts if t)
    if not text:
        return False
    system = JOURNAL_SYSTEM.format(name=cfg.companion_name, user=cfg.user_name)
    try:
        entry = run(system, f"CONVERSATIONS ON {day.isoformat()}:\n{text}").strip()
    except Exception as exc:
        logger.warning(f"memory: journal for {day} failed: {exc}")
        return False
    if not entry:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(entry + "\n")
    return True
