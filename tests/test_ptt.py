"""Ctrl+Shift+Space: tap tap = open/close · hold Space = your turn · tap = stop Rum talking."""

from omarum.ptt import DOUBLE_SECS, TAP_SECS, PushToTalk


def tap(p, t, open_=False, speaking=False):
    return p.press(t, open_, speaking) + p.release(t + 0.1)


def test_single_tap_while_closed_does_nothing():
    p = PushToTalk()
    assert tap(p, 0.0) == []
    assert p.tick(0.0 + TAP_SECS + 0.01) == []  # the key is already up: not a hold
    assert p.mode == "closed"


def test_double_tap_while_closed_opens_hands_free():
    p = PushToTalk()
    tap(p, 0.0)
    actions = p.press(0.1 + DOUBLE_SECS - 0.05, open_=False, speaking=False)
    assert actions == ["mic_open", "start"] and p.mode == "hands_free"
    assert p.release(0.5) == []  # the second tap's release does nothing more


def test_double_tap_while_open_closes():
    p = PushToTalk()
    tap(p, 0.0)
    p.press(0.3, False, False)  # second tap: opened
    p.release(0.35)
    tap(p, 5.0, open_=True)
    assert p.press(5.3, open_=True, speaking=False) == ["stop"] and p.mode == "closed"


def test_two_taps_too_far_apart_are_not_a_double():
    p = PushToTalk()
    tap(p, 0.0)
    assert p.press(0.1 + DOUBLE_SECS + 0.2, False, False) == []
    assert p.mode == "closed"


def test_single_tap_while_rum_talks_interrupts_instantly():
    p = PushToTalk()
    tap(p, 0.0); p.press(0.3, False, False); p.release(0.35)  # open hands-free
    actions = p.press(5.0, open_=True, speaking=True)
    assert actions[0] == "interrupt"  # on the press itself, no waiting for a second tap
    assert "stop" not in actions + p.release(5.1)
    assert p.mode == "hands_free"


def test_hold_while_closed_opens_for_your_turn():
    p = PushToTalk()
    assert p.press(0.0, False, False) == []  # could still be a tap
    assert p.tick(TAP_SECS + 0.01) == ["mic_open", "start", "hold_start"]
    assert p.mode == "hold"
    assert p.release(3.0) == ["hold_end", "mic_close"]  # Rum answers now; mic only while held


def test_hold_while_open_makes_rum_wait_until_release():
    p = PushToTalk()
    tap(p, 0.0); p.press(0.3, False, False); p.release(0.35)  # hands-free
    press = p.press(5.0, open_=True, speaking=False)
    assert "hold_start" in press
    assert p.tick(5.0 + TAP_SECS + 0.01) == []
    assert p.release(9.0) == ["hold_end"]  # hands-free: the mic stays open
    assert p.mode == "hands_free"


def test_hold_while_rum_talks_interrupts_and_takes_the_turn():
    p = PushToTalk()
    tap(p, 0.0); p.press(0.3, False, False); p.release(0.35)
    press = p.press(5.0, open_=True, speaking=True)
    assert press[0] == "interrupt" and "hold_start" in press


def test_bar_button_toggles():
    p = PushToTalk()
    assert p.toggle(open_=False) == ["mic_open", "start"] and p.mode == "hands_free"
    assert p.toggle(open_=True) == ["stop"] and p.mode == "closed"


def test_session_closed_elsewhere_resets():
    p = PushToTalk()
    tap(p, 0.0); p.press(0.3, False, False); p.release(0.35)
    p.closed()
    assert p.mode == "closed"
    assert p.press(10.0, open_=False, speaking=False) == []  # a fresh single press


def test_release_without_press_does_nothing():
    assert PushToTalk().release(1.0) == []
