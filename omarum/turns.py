"""When does the user's turn start? Words, not noise (spike feedback)."""

from __future__ import annotations

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
from pipecat.turns.user_mute.always_user_mute_strategy import AlwaysUserMuteStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from omarum.config import Config


class HoldMixin:
    """While the talk key is held, "your turn is over" waits; letting go sends it.

    If the voice detector never noticed the held speech, there is no turn waiting when the key
    comes up: then the transcript of the held audio (KeptWhisper records exactly that) ends the
    turn when it arrives, so letting go always hands the turn to Rum.
    """

    _held = False
    _pending = False
    _stop_on_transcript = False
    RELEASE_WAIT = 4.0  # seconds to wait for that transcript (nothing said: no turn)

    def hold(self) -> None:
        self._held = True
        self._stop_on_transcript = False

    async def release(self) -> None:
        import asyncio

        self._held = False
        if self._pending:
            self._pending = False
            await super().report_user_turn_stopped()
            return
        self._stop_on_transcript = True
        asyncio.get_running_loop().call_later(self.RELEASE_WAIT, self._expire)

    def _expire(self) -> None:
        self._stop_on_transcript = False

    async def process_frame(self, frame):
        import asyncio

        from pipecat.frames.frames import TranscriptionFrame

        result = await super().process_frame(frame)
        if self._stop_on_transcript and isinstance(frame, TranscriptionFrame) \
                and getattr(frame, "finalized", True):
            self._stop_on_transcript = False
            report = super().report_user_turn_stopped
            # A moment later, so the transcript has started the turn before it ends.
            asyncio.get_running_loop().call_later(0.05, lambda: asyncio.ensure_future(report()))
        return result

    async def report_user_turn_stopped(self, **kwargs):
        if self._held:
            self._pending = True  # Rum doesn't answer while you're holding the key
            return
        await super().report_user_turn_stopped(**kwargs)


def holdable_turn_stop():
    """Pipecat's smart-turn end-of-turn detection, plus HoldMixin."""
    from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
    from pipecat.turns.user_stop.turn_analyzer_user_turn_stop_strategy import TurnAnalyzerUserTurnStopStrategy

    class HoldableTurnStop(HoldMixin, TurnAnalyzerUserTurnStopStrategy):
        pass

    return HoldableTurnStop(turn_analyzer=LocalSmartTurnAnalyzerV3())


def turn_strategies(cfg: Config, stop=None) -> UserTurnStrategies:
    # No VAD start strategy: a click or breath must not cut Rum off. While Rum is
    # speaking, the user needs `interrupt_min_words` transcribed words to interrupt.
    # `stop`: the holdable smart-turn strategy the talk key controls (see HoldMixin).
    start = [MinWordsUserTurnStartStrategy(min_words=cfg.interrupt_min_words)]
    return UserTurnStrategies(start=start, stop=[stop]) if stop else UserTurnStrategies(start=start)


def vad_params(cfg: Config) -> VADParams:
    return VADParams(
        confidence=cfg.vad_confidence,
        start_secs=cfg.vad_start_secs,
        stop_secs=cfg.vad_stop_secs,
        min_volume=cfg.vad_min_volume,
    )


def mute_strategies(cfg: Config) -> list:
    """Without echo cancellation the mic hears Rum's own voice, so mute it while Rum talks."""
    return [AlwaysUserMuteStrategy()] if cfg.mute_while_speaking else []
