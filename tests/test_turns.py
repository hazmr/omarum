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
    assert p.stop_secs == 0.5


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


async def test_letting_go_ends_the_turn_when_the_transcript_arrives():
    """Seen 2026-11-21 14:47: the voice detector missed a held sentence, so after letting go
    Rum never took her turn. With the key, the transcript of the held audio ends the turn."""
    import asyncio

    from pipecat.frames.frames import TranscriptionFrame

    from omarum.turns import HoldMixin

    class Base:
        def __init__(self):
            self.stopped = 0

        async def report_user_turn_stopped(self, **kwargs):
            self.stopped += 1

        async def process_frame(self, frame):
            return None

    class S(HoldMixin, Base):
        pass

    s = S()
    s.hold()
    await s.release()  # the detector never saw speech: nothing pending
    assert s.stopped == 0
    t = TranscriptionFrame("what does this do", "user", "now")
    t.finalized = True
    await s.process_frame(t)
    await asyncio.sleep(0.15)
    assert s.stopped == 1
    await s.process_frame(t)  # later transcripts (hands-free talk) don't end turns by themselves
    await asyncio.sleep(0.15)
    assert s.stopped == 1


async def test_a_release_with_nothing_said_expires():
    import asyncio

    from omarum.turns import HoldMixin

    class Base:
        stopped = 0

        async def report_user_turn_stopped(self, **kwargs):
            self.stopped += 1

        async def process_frame(self, frame):
            return None

    class S(HoldMixin, Base):
        RELEASE_WAIT = 0.1

    s = S()
    s.hold()
    await s.release()
    await asyncio.sleep(0.2)
    assert s._stop_on_transcript is False
