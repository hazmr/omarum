"""Ctrl+Shift+Space (Ctrl+Shift stay down; only Space is timed):
double tap = open/close in every state · hold = your turn · single tap = only stops Rum talking."""

from omarum.ptt import DOUBLE_SECS, TAP_SECS, PushToTalk


def tap(p, t, open_, speaking=False):
    """A quick tap, with the extra "down" Hyprland sends together with every release."""
    return p.press(t, open_, speaking) + p.press(t + 0.1, open_, speaking) + p.release(t + 0.1)


def test_double_tap_opens_when_closed():  # log 14:13:26: two taps while closed did nothing
    p = PushToTalk()
    assert tap(p, 0.0, False) == []
    p.talk_mode = "hands_free"
    assert tap(p, 0.3, False) == ["mic_open", "start"] and p.mode == "hands_free"


def test_double_tap_closes_in_every_state():
    for speaking in (False, True):
        for start_mode in ("hold", "hands_free"):
            p = PushToTalk()
            p.mode = start_mode
            first = tap(p, 10.0, True, speaking)
            assert "stop" not in first  # a single tap never closes
            second = tap(p, 10.3, True, speaking)
            assert second[-1] == "stop" and p.mode == "closed", (speaking, start_mode)


def test_double_tap_closes_while_starting():
    p = PushToTalk()
    p.press(0.0, False, False); p.tick(0.4)  # holding: Rum is starting
    p.press(1.0, True, False); p.release(1.0)
    tap(p, 1.2, True)
    assert tap(p, 1.5, True)[-1] == "stop"


def test_release_only_taps_still_count():  # log 14:13:40: taps arrived as down+up together
    p = PushToTalk()
    p.mode = "hold"
    a = p.press(40.265, True, False) + p.release(40.265)
    b = p.press(40.461, True, False) + p.release(40.461)
    assert "stop" not in a and b[-1] == "stop"


def test_a_tap_after_a_hold_does_not_close():  # log 14:13:35: hold, let go, one tap -> closed
    p = PushToTalk()
    p.press(34.338, False, False)
    assert p.tick(34.658) == ["mic_open", "start", "hold_start"]
    assert p.press(35.325, True, False) == [] and p.release(35.326) == ["hold_end", "mic_close"]
    assert "stop" not in tap(p, 35.541, True)
    assert p.mode == "hold"


def test_single_tap_while_she_talks_only_stops_her():
    p = PushToTalk()
    p.toggle(open_=False)
    actions = tap(p, 5.0, True, speaking=True)
    assert actions[0] == "interrupt" and "stop" not in actions and p.mode == "hands_free"


def test_taps_too_far_apart_are_not_a_double():
    p = PushToTalk()
    tap(p, 0.0, False)
    assert tap(p, 0.1 + DOUBLE_SECS + 0.3, False) == [] and p.mode == "closed"


def test_hold_while_closed_opens_for_your_turn():
    p = PushToTalk()
    assert p.press(0.0, False, False) == []
    assert p.tick(TAP_SECS + 0.01) == ["mic_open", "start", "hold_start"]
    assert p.press(3.0, True, False) == []  # the extra down with the release
    assert p.release(3.0) == ["hold_end", "mic_close"]


def test_holding_while_rum_talks_stops_her_and_gives_you_the_turn():
    p = PushToTalk()
    p.mode = "hold"
    assert p.press(10.0, open_=True, speaking=True) == ["interrupt", "hold_start", "mic_open"]
    assert p.tick(10.4) == []
    assert p.release(12.0) == ["hold_end", "mic_close"]


def test_holding_in_hands_free_keeps_the_mic_on():
    p = PushToTalk()
    p.toggle(open_=False)
    p.press(5.0, True, False); p.tick(5.4)
    assert p.release(8.0) == ["hold_end"] and p.mode == "hands_free"


def test_open_but_out_of_sync_still_responds():
    p = PushToTalk()
    p.mode = "closed"
    tap(p, 10.0, True)
    assert tap(p, 10.3, True)[-1] == "stop"


def test_bar_button_toggles():
    p = PushToTalk()
    assert p.toggle(open_=False) == ["mic_open", "start"] and p.mode == "hands_free"
    assert p.toggle(open_=True) == ["stop"] and p.mode == "closed"


def test_session_closed_elsewhere_resets():
    p = PushToTalk()
    p.toggle(open_=False)
    p.closed()
    assert p.mode == "closed" and tap(p, 10.0, False) == []


def test_release_without_press_does_nothing():
    assert PushToTalk().release(1.0) == []


def test_push_to_talk_double_tap_opens_with_the_mic_off():
    """Talk mode = Push to talk (the default): after a double tap the mic is on only while Space is held."""
    p = PushToTalk()
    p.talk_mode = "push_to_talk"
    tap(p, 0.0, False)
    assert tap(p, 0.3, False) == ["mic_close", "start"] and p.mode == "hold"
    assert p.press(2.0, True, False) == ["hold_start", "mic_open"]
    assert p.release(4.0) == ["hold_end", "mic_close"]  # let go: she stops listening


def test_hands_free_talk_mode_keeps_the_mic_on():
    p = PushToTalk()
    p.talk_mode = "hands_free"
    tap(p, 0.0, False)
    p.talk_mode = "hands_free"
    assert tap(p, 0.3, False) == ["mic_open", "start"] and p.mode == "hands_free"


def test_push_to_talk_is_the_default():
    assert PushToTalk().talk_mode == "push_to_talk"
