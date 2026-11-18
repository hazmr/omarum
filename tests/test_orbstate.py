from omarum.orbstate import USER_VOICE_THRESHOLD, display_state, speaking_energy


def test_listening_shows_user_color_when_mic_hears_voice():
    assert display_state("listening", user_level=USER_VOICE_THRESHOLD + 0.1) == "user_speaking"


def test_listening_stays_listening_when_quiet():
    assert display_state("listening", user_level=0.02) == "listening"


def test_speaking_ignores_mic_echo():
    assert display_state("speaking", user_level=0.9) == "speaking"


def test_thinking_ignores_mic():
    assert display_state("thinking", user_level=0.9) == "thinking"


def test_speaking_energy_is_lively_and_bounded():
    vals = [speaking_energy(t / 30) for t in range(300)]
    assert all(0.0 <= v <= 1.0 for v in vals)
    assert max(vals) > 0.6 and min(vals) < 0.35  # it actually moves
