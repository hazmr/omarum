"""ElevenLabs account checks for settings: which voices this key can use, and why it can't speak.

ElevenLabs fails quietly inside the voice loop (a reply with no audio), so settings asks
directly and explains in plain words. Stdlib only (the settings window runs system Python).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from omarum.paths import DATA_DIR

API = "https://api.elevenlabs.io"
CACHE = DATA_DIR / "elevenlabs-voices.json"


KEY_ID_HINT = ("That's the key's ID, not the key: the key starts with sk_ and is shown only when you "
               "create or rotate it (elevenlabs.io → Profile → API keys)")


class ElevenLabsError(Exception):
    pass


def _explain(code: int, body: bytes) -> str:
    try:
        d = json.loads(body).get("detail") or {}
    except (ValueError, AttributeError):
        d = {}
    d = d if isinstance(d, dict) else {"message": str(d)}
    msg = str(d.get("message", ""))
    status = f"{d.get('status', '')} {d.get('code', '')}".lower()
    if "api_key_id_used_as_api_key" in status:
        return KEY_ID_HINT
    if "voices_read" in msg:
        return "Your key needs the 'Voices: Read' permission (elevenlabs.io → Profile → API keys → edit the key)"
    if "text_to_speech" in msg:
        return "Your key needs the 'Text to Speech' permission (elevenlabs.io → Profile → API keys → edit the key)"
    if "paid" in status or code == 402:
        return "This voice needs a paid ElevenLabs plan: choose one of your own or default voices"
    if "invalid_api_key" in status or (code == 401 and "permission" not in msg):
        return "The ElevenLabs key is not valid: paste it again"
    if "quota" in status or "quota" in msg.lower():
        return "Your ElevenLabs characters for this month are used up"
    return f"ElevenLabs said: {msg[:120] or f'error {code}'}"


def _call(key: str, path: str, body: dict | None = None, urlopen=None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        API + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"xi-api-key": key, "Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with (urlopen or urllib.request.urlopen)(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise ElevenLabsError(_explain(e.code, e.read())) from e
    except OSError as e:
        raise ElevenLabsError(f"Can't reach ElevenLabs: {e}") from e


def list_voices(key: str, urlopen=None) -> list[tuple[str, str, str]]:
    """(voice_id, name, category) the account has; default ("premade") voices first."""
    data = json.loads(_call(key, "/v1/voices", urlopen=urlopen))
    voices = [(v["voice_id"], v.get("name", v["voice_id"]), v.get("category", "")) for v in data.get("voices", [])]
    return sorted(voices, key=lambda v: (v[2] != "premade", v[1].lower()))


def check(key: str, voice_id: str, model: str, urlopen=None) -> str | None:
    """None if this key can speak with this voice, else why not (spends a few characters)."""
    if not key.strip():
        return "No ElevenLabs key yet"
    if not key.strip().startswith("sk_"):
        return KEY_ID_HINT
    try:
        audio = _call(key, f"/v1/text-to-speech/{voice_id}?output_format=pcm_16000",
                      {"text": "Hi.", "model_id": model}, urlopen=urlopen)
    except ElevenLabsError as e:
        return str(e)
    return None if audio else "ElevenLabs sent no audio"


def save_cache(voices: list[tuple[str, str, str]], path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(voices))


def load_cache(path: Path = CACHE) -> list[tuple[str, str, str]]:
    try:
        return [tuple(v) for v in json.loads(path.read_text())]
    except (OSError, ValueError):
        return []
