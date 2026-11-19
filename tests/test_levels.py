import struct

from pipecat.frames.frames import UserStartedSpeakingFrame
from pipecat.tests.utils import run_test

from omarum.levels import LatencyClock, StateTap, rms_level


def _square(amp: int, n: int = 1600) -> bytes:
    return b"".join(struct.pack("<h", amp if i % 2 else -amp) for i in range(n))


def test_rms_silence_is_zero():
    assert rms_level(bytes(3200)) == 0.0


def test_rms_loud_is_high():
    assert rms_level(_square(32767)) > 0.9


def test_rms_clamped():
    assert rms_level(_square(32767)) <= 1.0


def test_rms_empty():
    assert rms_level(b"") == 0.0


async def test_statetap_emits_user_speaking():
    events: list[dict] = []
    tap = StateTap(emit=events.append, who="user", clock=LatencyClock())
    down, _ = await run_test(
        tap,
        frames_to_send=[UserStartedSpeakingFrame()],
        expected_down_frames=[UserStartedSpeakingFrame],
    )
    assert {"type": "state", "state": "user_speaking"} in events


async def test_companion_speaking_starts_when_audio_plays():
    from pipecat.frames.frames import BotStartedSpeakingFrame
    from pipecat.processors.frame_processor import FrameDirection

    events: list[dict] = []
    tap = StateTap(emit=events.append, who="companion", clock=LatencyClock())
    await run_test(
        tap,
        frames_to_send=[BotStartedSpeakingFrame()],
        frames_to_send_direction=FrameDirection.UPSTREAM,
        expected_up_frames=[BotStartedSpeakingFrame],
    )
    assert {"type": "state", "state": "speaking"} in events


async def test_speaker_tap_emits_real_companion_levels():
    import struct

    from pipecat.frames.frames import OutputAudioRawFrame

    events: list[dict] = []
    tap = StateTap(emit=events.append, who="speaker", clock=LatencyClock())
    loud = struct.pack("<160h", *([20000, -20000] * 80))  # 10 ms at 16 kHz
    await run_test(
        tap,
        frames_to_send=[OutputAudioRawFrame(audio=loud, sample_rate=16000, num_channels=1)],
        expected_down_frames=[OutputAudioRawFrame],
    )
    levels = [e for e in events if e["type"] == "level"]
    assert levels and levels[0]["who"] == "companion" and levels[0]["value"] > 0.5


async def test_pre_speaker_companion_tap_sends_no_levels():
    import struct

    from pipecat.frames.frames import OutputAudioRawFrame

    events: list[dict] = []
    tap = StateTap(emit=events.append, who="companion", clock=LatencyClock())
    loud = struct.pack("<160h", *([20000, -20000] * 80))
    await run_test(
        tap,
        frames_to_send=[OutputAudioRawFrame(audio=loud, sample_rate=16000, num_channels=1)],
        expected_down_frames=[OutputAudioRawFrame],
    )
    assert not [e for e in events if e["type"] == "level"]
