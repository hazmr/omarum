"""Rum's ZONOS3-Mini voice: a client for Zyphra's local zonos3-server (streaming PCM)."""

from __future__ import annotations

import array
import json
import os
import shutil
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

ENGINE_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "omarum" / "engines" / "zonos3"
GGML_DIR = ENGINE_DIR / "servers" / "ggml"
SERVER_RATE = 44100


def float32_to_int16(buf: bytes) -> bytes:
    """Little-endian float32 PCM -> int16 PCM, clipped."""
    floats = array.array("f", buf[: len(buf) // 4 * 4])
    out = array.array("h", (int(max(-1.0, min(1.0, x)) * 32767) for x in floats))
    return out.tobytes()


class LeadingSilenceTrimmer:
    """Drops the quiet lead-in ZONOS3 puts before each sentence (int16 PCM, streamed)."""

    def __init__(self, threshold: int = 300, max_trim_samples: int = 7200) -> None:
        self.threshold = threshold
        self.budget = max_trim_samples  # never drop more than this (0.3 s at 24 kHz)
        self.started = False

    def feed(self, pcm: bytes) -> bytes:
        if self.started:
            return pcm
        samples = array.array("h", pcm)
        for i, v in enumerate(samples):
            if abs(v) >= self.threshold or i >= self.budget:
                self.started = True
                return samples[i:].tobytes()
        self.budget -= len(samples)
        if self.budget <= 0:
            self.started = True
        return b""


def pick_speaker(speakers: list[dict], wanted: str) -> str | None:
    """A speaker id from GET /v2/speakers: by exact id, else by name (case-insensitive), else the first."""
    if not speakers:
        return None
    for sp in speakers:
        if sp.get("id") == wanted:
            return sp["id"]
    needle = wanted.lower()
    for sp in speakers:
        if needle and needle in json.dumps({k: v for k, v in sp.items() if k != "id"}).lower():
            return sp["id"]
    return speakers[0]["id"]


def server_binary() -> Path | None:
    for build in ("build-vulkan", "build-cuda", "build"):
        b = GGML_DIR / build / "zonos3-server"
        if b.is_file():
            return b
    return None


def is_installed() -> bool:
    return server_binary() is not None and (GGML_DIR / "gguf" / "backbone-ptq.gguf").is_file()


def start_server(port: int) -> subprocess.Popen | None:
    """Launch zonos3-server once (it keeps the model loaded); None if not installed."""
    binary = server_binary()
    if binary is None:
        return None
    log = open(Path.home() / ".local" / "state" / "omarum" / "zonos3.log", "ab")
    args = [str(binary), str(GGML_DIR / "gguf" / "backbone-ptq.gguf"), "--port", str(port)]
    if binary.parent.name in ("build-vulkan", "build-cuda"):
        args.append("--gpu")  # Vulkan (e.g. Radeon iGPU) or CUDA: ~3x faster decode than CPU
    voices = GGML_DIR / "gguf" / "voices"
    if voices.is_dir():
        args += ["--tts-default-voices-dir", str(voices)]
    return subprocess.Popen(args, cwd=GGML_DIR, stdout=log, stderr=subprocess.STDOUT, preexec_fn=_die_with_parent)


def _die_with_parent() -> None:
    """Linux: SIGTERM this child when the daemon exits, however it exits."""
    import ctypes
    import signal

    PR_SET_PDEATHSIG = 1
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


def make_service(base_url: str, voice: str, language: str):
    import aiohttp
    from loguru import logger
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.settings import TTSSettings
    from pipecat.services.tts_service import TTSService
    from pipecat.utils.errors import ErrorCategory

    class Zonos3TTSService(TTSService):
        def __init__(self, **kwargs) -> None:
            super().__init__(settings=TTSSettings(model="zonos3-mini", voice=voice, language=None), **kwargs)
            self._session: aiohttp.ClientSession | None = None
            self._speaker: str | None = None

        async def _speaker_id(self) -> str | None:
            if self._speaker is None:
                async with self._session.get(f"{base_url}/v2/speakers") as resp:
                    speakers = (await resp.json()).get("speakers", [])
                self._speaker = pick_speaker(speakers, voice)
            return self._speaker

        async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
            from pipecat.audio.utils import create_stream_resampler

            self._session = self._session or aiohttp.ClientSession()
            resampler = create_stream_resampler()
            trimmer = LeadingSilenceTrimmer(max_trim_samples=int(self.sample_rate * 0.3))
            leftover = b""
            try:
                body = {"text": text, "language": language, "stream": True}
                speaker = await self._speaker_id()
                if speaker:
                    body["speaker_embedding_id"] = speaker
                await self.start_tts_usage_metrics(text)
                async with self._session.post(f"{base_url}/v2/generate", json=body) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"zonos3 {resp.status}: {(await resp.text())[:200]}")
                    async for chunk in resp.content.iter_chunked(8192):
                        await self.stop_ttfb_metrics()
                        data = leftover + chunk
                        cut = len(data) // 4 * 4
                        leftover = data[cut:]
                        pcm = trimmer.feed(
                            await resampler.resample(float32_to_int16(data[:cut]), SERVER_RATE, self.sample_rate)
                        )
                        if pcm:
                            yield TTSAudioRawFrame(audio=pcm, sample_rate=self.sample_rate, num_channels=1, context_id=context_id)
            except Exception as exc:  # server down, crashed, bad voice...
                logger.warning(f"zonos3 failed: {exc}")
                yield ErrorFrame(error=f"zonos3: {exc}", exception=exc, category=ErrorCategory.CONNECTIVITY)
            finally:
                await self.stop_ttfb_metrics()

        async def cleanup(self) -> None:
            await super().cleanup()
            if self._session:
                await self._session.close()

    return Zonos3TTSService()
