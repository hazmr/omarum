"""Ctrl+Shift+Space is a walkie-talkie: hold to talk, let go and Rum answers. Nothing else."""

from omarum.ptt import TAP_SECS, PushToTalk


def test_hold_while_closed_opens_for_your_turn():
    p = PushToTalk()
    assert p.press(0.0, False, False) == []  # a tap must not open Rum by accident
    assert p.tick(TAP_SECS + 0.01) == ["mic_open", "start", "hold_start"]
    assert p.mode == "hold"
    assert p.release(3.0) == ["hold_end", "mic_close"]  # let go: Rum answers; the mic is off again


def test_quick_tap_while_closed_does_nothing():
    p = PushToTalk()
    assert p.press(0.0, False, False) + p.release(0.1) == []
    assert p.tick(TAP_SECS + 0.01) == []
    assert p.mode == "closed"


def test_two_quick_taps_do_nothing_either():
    p = PushToTalk()
    for t in (0.0, 0.2, 0.4):
        assert p.press(t, False, False) + p.release(t + 0.08) == []
    assert p.mode == "closed"


def test_next_hold_in_the_same_conversation():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4); p.release(3.0)
    assert p.press(10.0, open_=True, speaking=False) == ["hold_start", "mic_open"]
    assert p.release(13.0) == ["hold_end", "mic_close"]
    assert p.mode == "hold"


def test_holding_while_rum_talks_stops_her_and_gives_you_the_turn():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4); p.release(3.0)
    assert p.press(10.0, open_=True, speaking=True) == ["interrupt", "hold_start", "mic_open"]


def test_one_tap_while_open_closes_rum():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4); p.release(3.0)  # a conversation is open
    actions = p.press(10.0, open_=True, speaking=False) + p.release(10.1)
    assert actions[-1] == "stop" and p.mode == "closed"


def test_a_tap_while_she_talks_stops_her_and_closes():
    p = PushToTalk()
    p.toggle(open_=False)
    actions = p.press(5.0, open_=True, speaking=True) + p.release(5.1)
    assert actions[0] == "interrupt" and actions[-1] == "stop"


def test_a_hold_while_open_never_closes():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4); p.release(3.0)
    actions = p.press(10.0, True, False) + p.release(12.0)
    assert "stop" not in actions and p.mode == "hold"


def test_holding_in_hands_free_keeps_the_mic_on_after_release():
    p = PushToTalk()
    p.toggle(open_=False)  # the bar orb: hands-free
    assert p.press(5.0, open_=True, speaking=False) == ["hold_start", "mic_open"]
    assert p.release(8.0) == ["hold_end"]
    assert p.mode == "hands_free"


def test_bar_button_toggles():
    p = PushToTalk()
    assert p.toggle(open_=False) == ["mic_open", "start"] and p.mode == "hands_free"
    assert p.toggle(open_=True) == ["stop"] and p.mode == "closed"


def test_session_closed_elsewhere_resets():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4)
    p.closed()
    assert p.mode == "closed" and p.press(10.0, open_=False, speaking=False) == []


def test_release_without_press_does_nothing():
    assert PushToTalk().release(1.0) == []
