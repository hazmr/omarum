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
from omarum.farewelltap import FarewellTap
from omarum.screenctx import ScreenContext
from omarum.config import Config
from omarum.levels import LatencyClock, StateTap
from omarum.micgate import Breaker, MicGate
from omarum.volume import Volume
from omarum.recorder import Session, TranscriptTap
from omarum.voices import available_voices, build_tts, load_env_file, voice_chain
from omarum.turns import mute_strategies, turn_strategies, vad_params
from omarum.models import make_stt, resolve_whisper_model

Emit = Callable[[dict], None]



def noise_filter():
    """RNNoise on the mic: cuts fans, typing and room noise before Rum listens. None if unavailable."""
    try:
        from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

        return RNNoiseFilter()
    except Exception as exc:  # pyrnnoise missing or broken: Rum still works, just without the filter
        logger.warning(f"noise filter off: {exc}")
        return None

def build_pipeline(cfg: Config, emit: Emit, store=None) -> tuple[PipelineTask, Callable[[], Awaitable[None]], Session]:
    store = store or Store()
    store.ensure()
    from omarum import firstmeet

    first_meeting = firstmeet.is_first_meeting(store)  # before this session's folder exists
    clock = LatencyClock()
    session = Session(store, cfg, datetime.now())
    session.first_meeting = first_meeting
    transport = LocalAudioTransport(
        # 80 ms output chunks (default 40): fewer chances to run dry under load, which crackles.
        LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=8,
                                  audio_in_filter=noise_filter())
    )
    from omarum.volume import big_output_buffer

    big_output_buffer(transport.output()._py_audio)  # no crackle when the machine is busy

    from omarum.models import cached_whisper_model

    class KeptWhisper(WhisperSTTService):
        """Pipecat's Whisper, but the model stays loaded between conversations."""

        def _load(self):
            self._model = cached_whisper_model(self._settings.model, self._device, self._compute_type)
            unsupported = self._unsupported_language()
            if unsupported:
                raise ValueError(unsupported)

    def whisper(model: str, device: str, compute: str) -> WhisperSTTService:
        logger.info(f"whisper: {model} on {device}")
        return KeptWhisper(
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

    session.meta = {"brain": brains.label(cfg), "voices": voice_chain(cfg, available_voices(env, cfg)), "latency_ms": clock.samples}
    # The persona travels with the conversation, so API brains get it too; the CLI brains
    # skip system messages (they get the persona their own way).
    context = LLMContext(messages=[{"role": "system", "content": system_prompt}])
    from omarum.turns import holdable_turn_stop

    turn_hold = holdable_turn_stop()  # the talk key holds your turn open (daemon: hold_start/hold_end)
    session.turn_hold = turn_hold
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=vad_params(cfg)),
            user_turn_strategies=turn_strategies(cfg, stop=turn_hold),
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
        FarewellTap(emit),  # "bye", "good night": Rum says goodbye, then closes
        aggregators.user(),
        breaker,
        # The code on screen, and a screenshot when you ask Rum to look, go with what you said.
        *([ScreenContext(code=cfg.screen_awareness, look=cfg.screen_look)]
          if cfg.screen_awareness or cfg.screen_look else []),
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

    if first_meeting:
        from pipecat.frames.frames import LLMRunFrame

        @task.event_handler("on_pipeline_started")
        async def _speak_first(_task, _frame):
            # The first meeting: Rum says hello before the user says anything.
            context.add_message({"role": "user", "content": firstmeet.OPENER})
            await task.queue_frames([LLMRunFrame()])

    @task.event_handler("on_pipeline_error")
    async def _show_error(_task, frame):
        # The brain and the ears: say why on the panel. Voice errors stay quiet (they fail over).
        if frame.processor is llm and not getattr(llm, "reports_own_errors", False):
            emit({"type": "state", "state": "error", "reason": brains.error_reason(brains.label(cfg).split(" · ")[0], str(frame.error))})
        elif frame.processor is stt:
            emit({"type": "state", "state": "error", "reason": f"Speech recognition failed: {str(frame.error).split('failed:', 1)[-1].strip()[:140]}"})

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
