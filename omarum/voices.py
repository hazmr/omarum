"""Rum's voice. The user picks one; if it fails, Rum moves down this order:
ElevenLabs (cloud) -> ZONOS3-Mini (local) -> Kokoro (local, always there).
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarum" / "env"
ORDER = ["elevenlabs", "zonos3", "kokoro"]
LAST_RESORT = "kokoro"


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


def available_voices(env: dict[str, str], cfg=None) -> set[str]:
    from omarum import zonos3_tts

    have = {"kokoro"}
    key = env.get("ELEVENLABS_API_KEY", "").strip()
    # A real key starts with sk_ (a pasted key ID doesn't), and a voice must be chosen;
    # otherwise skip ElevenLabs instead of failing on every sentence.
    if key.startswith("sk_") and (cfg is None or getattr(cfg, "elevenlabs_voice_id", "")):
        have.add("elevenlabs")
    if zonos3_tts.is_installed():
        have.add("zonos3")
    return have


def voice_chain(cfg, available: set[str]) -> list[str]:
    """The chosen voice, then the ones after it in ORDER, skipping what isn't available."""
    if cfg.voice_primary not in ORDER:
        return [cfg.voice_primary]  # e.g. "piper": a manual choice, no chain
    chain = [v for v in ORDER[ORDER.index(cfg.voice_primary):] if v in available]
    return chain or [LAST_RESORT]


def should_fail_over(category) -> bool:
    """Errors that mean "this voice won't work right now": move to the next one.

    Pipecat only fails over on bad credentials/requests; a used-up free allowance,
    a dropped connection or a crashed local server should switch voices too.
    """
    from pipecat.utils.errors import ErrorCategory as C

    return category in {C.AUTHENTICATION, C.AUTHORIZATION, C.INVALID_REQUEST,
                        C.QUOTA, C.RATE_LIMIT, C.CONNECTIVITY, C.SERVER}


def build_tts(cfg, env: dict[str, str]):
    """One TTS service, or a failover switcher over the chain."""
    from loguru import logger

    names = voice_chain(cfg, available_voices(env, cfg))
    services = [_make(name, cfg, env) for name in names]
    logger.info(f"voices: {names}")
    if len(services) == 1:
        return services[0]
    from pipecat.pipeline.service_switcher import ServiceSwitcher, ServiceSwitcherStrategyFailover

    for svc in services[:-1]:
        @svc.event_handler("on_error")
        async def _maybe_fail_over(service, error):
            if should_fail_over(error.category) and service.is_usable:
                logger.warning(f"voice {service.name} unavailable ({error.category}); switching")
                await service.set_usable(False)

    return ServiceSwitcher(services=services, strategy_type=ServiceSwitcherStrategyFailover)


def _make(name: str, cfg, env: dict[str, str]):
    from omarum.models import MODELS_DIR

    if name == "elevenlabs":
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        return ElevenLabsTTSService(
            api_key=env["ELEVENLABS_API_KEY"],
            settings=ElevenLabsTTSService.Settings(voice=cfg.elevenlabs_voice_id, model=cfg.elevenlabs_model),
        )
    if name == "zonos3":
        from omarum import zonos3_tts

        return zonos3_tts.make_service(f"http://127.0.0.1:{cfg.zonos3_port}", cfg.zonos3_voice, cfg.zonos3_language)
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
