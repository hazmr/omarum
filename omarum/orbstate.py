"""What the orb shows, from daemon state plus live levels. Stdlib only (system Python)."""

from __future__ import annotations

import math

USER_VOICE_THRESHOLD = 0.25  # mic level that means "you're talking" (levels are boosted, see levels.rms_level)


def display_state(state: str, user_level: float) -> str:
    """The daemon only learns a turn started after transcription; the mic level is instant."""
    if state in ("listening", "user_speaking"):
        return "user_speaking" if user_level >= USER_VOICE_THRESHOLD else state
    return state


def speaking_energy(t: float) -> float:
    """Voice-like movement while Rum talks (syllables inside words), 0..1."""
    syllables = abs(math.sin(t * 7.3)) * abs(math.sin(t * 2.1))
    words = 0.5 + 0.5 * math.sin(t * 0.9)
    return min(1.0, (0.25 + syllables * 0.9) * (0.4 + 0.6 * words))
