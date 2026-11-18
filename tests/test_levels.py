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
