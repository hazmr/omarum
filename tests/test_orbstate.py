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


def test_energy_follows_real_level_with_fast_attack():
    from omarum.orbstate import follow_energy

    e = follow_energy(0.0, 1.0)
    assert e >= 0.5  # syllable onsets show within one frame
    assert follow_energy(1.0, 0.0) >= 0.8  # but fades gently


def test_fallback_rhythm_only_when_no_real_levels():
    from omarum.orbstate import companion_target

    assert companion_target(real_level=0.3, since_level=0.05, t=1.0) == 0.6  # doubled: TTS is quieter than the mic
    assert companion_target(real_level=0.7, since_level=0.05, t=1.0) == 1.0  # capped
    assert companion_target(real_level=0.0, since_level=2.0, t=1.0) > 0  # no levels at all: keep it alive
    assert companion_target(real_level=0.0, since_level=0.1, t=1.0) == 0.0  # a real pause stays still
