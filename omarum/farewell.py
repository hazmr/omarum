"""Saying goodbye closes Rum: "bye", "good night", "that's all", "stop listening". Stdlib only.

Only when the goodbye is what they're saying (a short utterance, or how it ends), not a word
inside a longer sentence like "I'll fix it later".
"""

from __future__ import annotations

import re

_BYE = re.compile(
    r"\b(bye( bye)?|good ?bye|see (you|ya)( (later|tomorrow|soon|then))?|good ?night"
    r"|that'?s all( for (now|today))?|talk (to you )?(later|tomorrow|soon)|stop listening"
    r"|(i'?m|we'?re) done for (now|today)|catch you later)\b",
    re.IGNORECASE)
_WORDS = re.compile(r"[\w']+")


def is_farewell(said: str) -> bool:
    """A goodbye that ends what they said: at most two words after it ("Goodbye Rum", "that's all, thanks")."""
    text = (said or "").strip()
    if not text or text.endswith("?"):
        return False
    return any(len(_WORDS.findall(text[m.end():])) <= 2 for m in _BYE.finditer(text))
