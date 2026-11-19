from omarum.ptt import TAP_SECS, PushToTalk


def test_hold_when_closed_starts_session_with_mic_open_then_closes_mic():
    p = PushToTalk()
    assert p.press(0.0, open_=False, speaking=False) == ["mic_open", "start"]
    assert p.release(1.5) == ["mic_close"]
    assert p.mode == "hold"


def test_tap_when_closed_starts_hands_free():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    assert p.release(TAP_SECS / 2) == ["hands_free"]
    assert p.mode == "hands_free"


def test_tap_in_hands_free_closes():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    p.release(0.1)
    assert p.press(5.0, open_=True, speaking=False) == []
    assert p.release(5.1) == ["stop"]
    assert p.mode == "closed"


def test_hold_while_rum_speaks_interrupts():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    p.release(2.0)
    assert p.press(5.0, open_=True, speaking=True) == ["interrupt", "mic_open"]
    assert p.release(7.0) == ["mic_close"]


def test_hold_in_hands_free_keeps_mic_open_after_release():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    p.release(0.1)  # hands-free
    assert p.press(5.0, open_=True, speaking=True) == ["interrupt"]  # mic already open
    assert p.release(6.0) == []  # still hands-free
    assert p.mode == "hands_free"


def test_tap_in_hold_mode_switches_to_hands_free():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    p.release(2.0)  # hold session
    p.press(5.0, open_=True, speaking=False)
    assert p.release(5.1) == ["hands_free"]


def test_session_closed_elsewhere_resets():
    p = PushToTalk()
    p.press(0.0, open_=False, speaking=False)
    p.release(0.1)
    p.closed()  # idle timeout or the old toggle command
    assert p.press(9.0, open_=False, speaking=False) == ["mic_open", "start"]


def test_release_without_press_does_nothing():
    assert PushToTalk().release(1.0) == []
