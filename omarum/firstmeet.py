"""The first meeting: the first time Rum and the user ever talk. Stdlib only.

It's the first meeting until a conversation with real words in it has been saved and Rum
has no notes about the user. Rum speaks first, gets to know them, and picks its own name;
the names said in that talk ("My name is Nova", "call me Haz") are saved to the settings.
"""

from __future__ import annotations

import re

FIRST_MEETING = """\
## This is your first meeting
This is the very first time you and the person you're talking to have ever spoken. You were just switched on for them, and you know nothing about them yet. Be curious about everything, a little excited, and honest that this is all new to you.
- You speak first: say hello warmly and simply, like meeting someone new.
- Get to know them as a person, in a real back-and-forth: what to call them (the app thinks their name is "{user}", but check), what they do, what they care about, how their day is. Tell them things about yourself too; it's not an interview.
- You don't have a name of your own yet. "{name}" is only what the app called you. Early in the talk, think out loud for a moment about what you'd like to be called, then choose a name you really like (you may keep "{name}" if it feels right). Say it once, clearly, in exactly this form: "My name is <Name>." From then on, that's your name.
"""

OPENER = "(You've just been switched on and this first conversation has started. Say hello.)"

_COMPANION = re.compile(r"\bMy name is ([A-Z][a-zA-Z'-]{1,19})\b")
_USER = re.compile(r"\b(?:[Mm]y name is|[Cc]all me|I'm called|I am called)\s+([A-Z][a-zA-Z'-]{1,19})\b")
_NOT_NAMES = {"The", "A", "An", "Not", "Just", "Really", "Something", "Nothing", "It", "That", "This"}


def is_first_meeting(store) -> bool:
    from omarum.recorder import read_transcript

    try:
        if store.profile_path.read_text().strip():
            return False
    except OSError:
        pass
    root = store.conversations_dir
    if root.is_dir():
        for t in root.glob("*/*/transcript.jsonl"):
            if read_transcript(t):
                return False
    return True


def prompt_section(cfg) -> str:
    return FIRST_MEETING.replace("{user}", cfg.user_name).replace("{name}", cfg.companion_name)


def chosen_names(rows: list[dict]) -> tuple[str | None, str | None]:
    """(the name Rum chose, the name the user gave), the first of each said in the talk."""
    companion = user = None
    for r in rows:
        text = r.get("text", "")
        if r.get("who") == "companion" and companion is None:
            m = _COMPANION.search(text)
            if m and m.group(1) not in _NOT_NAMES:
                companion = m.group(1)
        elif r.get("who") == "user" and user is None:
            m = _USER.search(text)
            if m and m.group(1) not in _NOT_NAMES:
                user = m.group(1)
    return companion, user


def name_updates(rows: list[dict], cfg) -> dict:
    """Settings to save after the first talk: the names that were chosen and differ from now."""
    companion, user = chosen_names(rows)
    out = {}
    if companion and companion != cfg.companion_name:
        out["companion_name"] = companion
    if user and user != cfg.user_name:
        out["user_name"] = user
    return out
