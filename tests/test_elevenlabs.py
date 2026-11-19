import io
import json
import urllib.error

import pytest

from omarum import elevenlabs


def _resp(code, body):
    if code == 200:
        class R(io.BytesIO):
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda req, timeout=None: R(json.dumps(body).encode() if not isinstance(body, bytes) else body)

    def fail(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(json.dumps(body).encode()))
    return fail


def _detail(status, message, code="x"):
    return {"detail": {"status": status, "code": code, "message": message}}


def test_lists_voices_premade_first():
    body = {"voices": [{"voice_id": "c1", "name": "My clone", "category": "cloned"},
                       {"voice_id": "p1", "name": "Sarah", "category": "premade"},
                       {"voice_id": "l1", "name": "Library guy", "category": "professional"}]}
    voices = elevenlabs.list_voices("k", urlopen=_resp(200, body))
    assert voices[0] == ("p1", "Sarah", "premade")
    assert {v[0] for v in voices} == {"c1", "p1", "l1"}


def test_missing_voices_permission_is_explained():
    err = _detail("missing_permissions", "The API key you used is missing the permission voices_read to execute this operation.")
    with pytest.raises(elevenlabs.ElevenLabsError, match="Voices: Read"):
        elevenlabs.list_voices("k", urlopen=_resp(401, err))


def test_check_explains_paid_voice_and_bad_key():
    paid = _detail("payment_required", "Free users cannot use library voices via the API.", "paid_plan_required")
    assert "paid" in elevenlabs.check("sk_k", "v", "m", urlopen=_resp(402, paid)).lower()
    bad = _detail("invalid_api_key", "Invalid API key", "invalid_api_key")
    assert "not valid" in elevenlabs.check("sk_k", "v", "m", urlopen=_resp(401, bad))
    assert elevenlabs.check("sk_k", "v", "m", urlopen=_resp(200, b"\x00\x01" * 100)) is None
    assert "no elevenlabs key" in elevenlabs.check("", "v", "m").lower()


def test_voice_cache_roundtrip(tmp_path):
    f = tmp_path / "voices.json"
    elevenlabs.save_cache([("p1", "Sarah", "premade")], f)
    assert elevenlabs.load_cache(f) == [("p1", "Sarah", "premade")]
    assert elevenlabs.load_cache(tmp_path / "missing.json") == []


def test_key_id_pasted_instead_of_the_key_is_explained():
    body = _detail("api_key_id_used_as_api_key",
                   "API key ID used as API key - only valid API keys can be used. API keys start with 'sk_'",
                   "invalid_api_key")
    why = elevenlabs.check("sk_k", "v", "m", urlopen=_resp(400, body))
    assert "ID" in why and "sk_" in why
    assert "sk_" in elevenlabs.check("0" * 64, "v", "m")  # caught before even asking ElevenLabs
