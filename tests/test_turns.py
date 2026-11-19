from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
from pipecat.turns.user_start.vad_user_turn_start_strategy import VADUserTurnStartStrategy

from omarum.config import Config
from omarum.turns import turn_strategies, vad_params


def test_noise_cannot_interrupt_only_words_can():
    s = turn_strategies(Config())
    assert len(s.start) == 1
    assert isinstance(s.start[0], MinWordsUserTurnStartStrategy)
    assert s.start[0]._min_words == 3
    assert not any(isinstance(x, VADUserTurnStartStrategy) for x in s.start)


def test_min_words_configurable():
    assert turn_strategies(Config(interrupt_min_words=5)).start[0]._min_words == 5


def test_vad_is_stricter_than_pipecat_defaults():
    p = vad_params(Config())
    assert p.confidence == 0.8
    assert p.start_secs == 0.3
    assert p.min_volume == 0.7
    assert p.stop_secs == 0.8


def test_mic_muted_while_rum_speaks_by_default():
    from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy

    from omarum.turns import mute_strategies

    s = mute_strategies(Config())
    assert len(s) == 1 and isinstance(s[0], AlwaysUserMuteStrategy)


def test_mute_can_be_disabled_for_echo_cancelled_setups():
    from omarum.turns import mute_strategies

    assert mute_strategies(Config(mute_while_speaking=False)) == []


async def test_rum_waits_while_you_hold_and_answers_on_release():
    from pipecat.turns.user_stop.base_user_turn_stop_strategy import BaseUserTurnStopStrategy

    from omarum.turns import HoldMixin

    class Strategy(HoldMixin, BaseUserTurnStopStrategy):
        pass

    s = Strategy()
    fired = []

    @s.event_handler("on_user_turn_stopped")
    async def _stopped(_s, _params):
        fired.append(1)

    s.hold()
    await s.report_user_turn_stopped()  # the smart-turn model thinks you're done: not while held
    assert fired == []
    await s.release()                   # you let go: the held-back decision goes out now
    assert fired == [1]
    await s.release()                   # nothing pending: nothing more
    assert fired == [1]
    await s.report_user_turn_stopped()  # not held: works as before
    assert fired == [1, 1]
