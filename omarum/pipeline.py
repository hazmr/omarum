"""The voice loop: mic -> VAD -> Whisper -> any brain -> voice -> speakers."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Awaitable, Callable

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from omarum.context import build_system_prompt
from omarum.store import Store
from omarum import brains
from omarum.config import Config
from omarum.levels import LatencyClock, StateTap
from omarum.micgate import Breaker, MicGate
from omarum.volume import Volume
from omarum.recorder import Session, TranscriptTap
from omarum.voices import available_voices, build_tts, load_env_file, voice_chain
from omarum.turns import mute_strategies, turn_strategies, vad_params
from omarum.models import make_stt, resolve_whisper_model

Emit = Callable[[dict], None]


def build_pipeline(cfg: Config, emit: Emit, store=None) -> tuple[PipelineTask, Callable[[], Awaitable[None]], Session]:
    store = store or Store()
    store.ensure()
    clock = LatencyClock()
    session = Session(store, cfg, datetime.now())
    transport = LocalAudioTransport(
        LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True)
    )
    def whisper(model: str, device: str, compute: str) -> WhisperSTTService:
        logger.info(f"whisper: {model} on {device}")
        return WhisperSTTService(
            settings=WhisperSTTService.Settings(
                model=resolve_whisper_model(model), no_speech_prob=cfg.whisper_no_speech_prob
            ),
            device=device,
            compute_type=compute,
            ttfs_p99_latency=cfg.whisper_ttfs_p99,
        )

    stt = make_stt(cfg, whisper)
    env = {**load_env_file(), **os.environ}
    system_prompt = build_system_prompt(cfg, store, datetime.now())
    llm = brains.make_llm(
        cfg, env, system_prompt,
        on_error=lambda reason: emit({"type": "state", "state": "error", "reason": reason}),
    )
    tts = build_tts(cfg, env)
    recorder = AudioBufferProcessor(num_channels=1, auto_start_recording=True)

    @recorder.event_handler("on_track_audio_data")
    async def _keep_audio(_proc, user_audio, bot_audio, sample_rate, _channels):
        session.add_audio(user_audio, bot_audio, sample_rate)

    session.meta = {"brain": brains.label(cfg), "voices": voice_chain(cfg, available_voices(env)), "latency_ms": clock.samples}
    # The persona travels with the conversation, so API brains get it too; the CLI brains
    # skip system messages (they get the persona their own way).
    context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=vad_params(cfg)),
            user_turn_strategies=turn_strategies(cfg),
            user_mute_strategies=mute_strategies(cfg),
        ),
    )
    gate = MicGate(open_=True)
    gate.breaker = breaker = Breaker()
    session.gate = gate  # the daemon opens/closes it for push-to-talk and uses it to interrupt
    pipeline = Pipeline([
        transport.input(),
        gate,
        StateTap(emit, "user", clock),
        stt,
        TranscriptTap(session.transcript, "user"),
        aggregators.user(),
        breaker,
        llm,
        TranscriptTap(session.transcript, "companion"),
        tts,
        StateTap(emit, "companion", clock),
        Volume(cfg.voice_volume / 100),
        transport.output(),
        StateTap(emit, "speaker", clock),
        recorder,
        aggregators.assistant(),
    ])
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=False))

    async def stop() -> None:
        # Cancel, don't EndFrame: an EndFrame waits for queued speech to finish playing.
        await task.cancel(reason="closed by user")

    return task, stop, session


async def _main() -> None:
    """Smoke test: one session that prints every event. Ctrl+C to quit."""
    from pipecat.pipeline.runner import PipelineRunner

    from omarum.config import load_config

    def emit(msg: dict) -> None:
        if msg["type"] != "level":
            print(msg, flush=True)

    task, _, _ = build_pipeline(load_config(), emit)
    emit({"type": "state", "state": "listening"})
    await PipelineRunner(handle_sigint=True).run(task)


if __name__ == "__main__":
    asyncio.run(_main())
