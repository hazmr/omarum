"""When does the user's turn start? Words, not noise (spike feedback)."""

from __future__ import annotations

from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from omarum.config import Config


def turn_strategies(cfg: Config) -> UserTurnStrategies:
    # No VAD start strategy: a click or breath must not cut Rum off. While Rum is
    # speaking, the user needs `interrupt_min_words` transcribed words to interrupt.
    return UserTurnStrategies(start=[MinWordsUserTurnStartStrategy(min_words=cfg.interrupt_min_words)])


def vad_params(cfg: Config) -> VADParams:
    return VADParams(
        confidence=cfg.vad_confidence,
        start_secs=cfg.vad_start_secs,
        stop_secs=cfg.vad_stop_secs,
        min_volume=cfg.vad_min_volume,
    )
