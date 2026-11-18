"""Rum's voice: a cloud voice first, a local open-source voice as the fallback."""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarum" / "env"
LOCAL_FALLBACK = "kokoro"


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    """KEY=value lines (written by the key-saving command); comments and junk ignored."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    env = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() and " " not in key.strip():
            env[key.strip()] = value.strip()
    return env


def voice_chain(cfg, env: dict[str, str]) -> list[str]:
    """Which voices to try, in order. The cloud voice needs its key."""
    if cfg.voice_primary == "elevenlabs":
        return ["elevenlabs", LOCAL_FALLBACK] if env.get("ELEVENLABS_API_KEY") else [LOCAL_FALLBACK]
    return [cfg.voice_primary]


def build_tts(cfg, env: dict[str, str]):
    """One TTS service, or a failover switcher over the chain."""
    from loguru import logger

    services = [_make(name, cfg, env) for name in voice_chain(cfg, env)]
    logger.info(f"voices: {[type(s).__name__ for s in services]}")
    if len(services) == 1:
        return services[0]
    from pipecat.pipeline.service_switcher import ServiceSwitcher, ServiceSwitcherStrategyFailover

    return ServiceSwitcher(services=services, strategy_type=ServiceSwitcherStrategyFailover)


def _make(name: str, cfg, env: dict[str, str]):
    from omarum.models import MODELS_DIR

    if name == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        return ElevenLabsTTSService(
            api_key=env["ELEVENLABS_API_KEY"],
            settings=ElevenLabsTTSService.Settings(voice=cfg.elevenlabs_voice_id, model=cfg.elevenlabs_model),
        )
    if name == "kokoro":
        from pipecat.services.kokoro.tts import KokoroTTSService

        d = MODELS_DIR / "kokoro"
        return KokoroTTSService(
            model_path=str(d / "kokoro-v1.0.onnx"),
            voices_path=str(d / "voices-v1.0.bin"),
            settings=KokoroTTSService.Settings(voice=cfg.kokoro_voice),
        )
    if name == "piper":
        from pipecat.services.piper.tts import PiperTTSService

        return PiperTTSService(
            settings=PiperTTSService.Settings(voice=cfg.piper_voice),
            download_dir=MODELS_DIR / "piper",
        )
    raise ValueError(f"unknown voice engine {name!r}")
