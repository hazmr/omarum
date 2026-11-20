"""Does the ElevenLabs key actually work? Checked once per key and voice, in the background.

A revoked key made every reply silent (ElevenLabs sent no audio) until three failures in a row
switched voices. With this, Rum skips ElevenLabs while its key or voice doesn't work. Stdlib only.
"""

from __future__ import annotations

import hashlib

_RESULTS: dict[tuple, str | None] = {}  # (key hash, voice, model) -> None (works) or the reason


def _id(env: dict, cfg) -> tuple:
    key = env.get("ELEVENLABS_API_KEY", "").strip()
    return (hashlib.sha256(key.encode()).hexdigest(), cfg.elevenlabs_voice_id, cfg.elevenlabs_model)


def check_elevenlabs(env: dict, cfg, check=None) -> str | None:
    """Test the key once (a few characters of speech); remember the answer."""
    ident = _id(env, cfg)
    if ident not in _RESULTS:
        check = check or _default_check()
        _RESULTS[ident] = check(env.get("ELEVENLABS_API_KEY", "").strip(), cfg.elevenlabs_voice_id, cfg.elevenlabs_model)
    return _RESULTS[ident]


def _default_check():
    from omarum.elevenlabs import check

    return check


def reason(env: dict, cfg) -> str | None:
    """Why ElevenLabs can't speak, if that's known; None if it works or isn't checked yet."""
    return _RESULTS.get(_id(env, cfg))


def known_broken(env: dict, cfg) -> bool:
    return reason(env, cfg) is not None
