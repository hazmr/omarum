import pytest


@pytest.fixture(autouse=True)
def _no_real_elevenlabs(monkeypatch):
    """Tests never call ElevenLabs (or spend characters) with the real key in ~/.config/omarum/env."""
    from omarum import voicehealth

    monkeypatch.setattr(voicehealth, "_default_check", lambda: (lambda *a, **k: None))
    monkeypatch.setattr(voicehealth, "_RESULTS", {})
