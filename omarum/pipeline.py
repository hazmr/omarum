"""The voice loop: mic -> VAD -> Whisper -> Claude Code -> Piper -> speakers."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams

from omarum import persona
from omarum.claude_code_llm import DATA_DIR, ClaudeCodeLLMService
from omarum.config import Config
from omarum.levels import LatencyClock, StateTap
from omarum.models import pick_whisper, resolve_whisper_model

Emit = Callable[[dict], None]


def build_pipeline(cfg: Config, emit: Emit) -> tuple[PipelineTask, Callable[[], Awaitable[None]]]:
    clock = LatencyClock()
    transport = LocalAudioTransport(
        LocalAudioTransportParams(audio_in_enabled=True, audio_out_enabled=True)
    )
    model, device, compute = pick_whisper(cfg)
    logger.info(f"whisper: {model} on {device}")
    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(model=resolve_whisper_model(model)),
        device=device,
        compute_type=compute,
    )
    llm = ClaudeCodeLLMService(
        model=cfg.brain_model,
        system_prompt=persona.render(cfg),
        on_error=lambda reason: emit({"type": "state", "state": "error", "reason": reason}),
    )
    tts = PiperTTSService(
        settings=PiperTTSService.Settings(voice=cfg.piper_voice),
        download_dir=DATA_DIR / "models" / "piper",
    )
    context = LLMContext()
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=cfg.vad_stop_secs)),
        ),
    )
    pipeline = Pipeline([
        transport.input(),
        StateTap(emit, "user", clock),
        stt,
        aggregators.user(),
        llm,
        tts,
        StateTap(emit, "companion", clock),
        transport.output(),
        aggregators.assistant(),
    ])
    task = PipelineTask(pipeline, params=PipelineParams(enable_metrics=False))

    async def stop() -> None:
        await task.queue_frame(EndFrame())

    return task, stop


async def _main() -> None:
    """Smoke test: one session that prints every event. Ctrl+C to quit."""
    from pipecat.pipeline.runner import PipelineRunner

    from omarum.config import load_config

    def emit(msg: dict) -> None:
        if msg["type"] != "level":
            print(msg, flush=True)

    task, _ = build_pipeline(load_config(), emit)
    emit({"type": "state", "state": "listening"})
    await PipelineRunner(handle_sigint=True).run(task)


if __name__ == "__main__":
    asyncio.run(_main())
