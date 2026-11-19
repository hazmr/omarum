from pipecat.frames.frames import InputAudioRawFrame
from pipecat.tests.utils import run_test

from omarum.micgate import MicGate

LOUD = b"\x10\x27" * 160


async def _through(gate: MicGate) -> bytes:
    down, _ = await run_test(
        gate,
        frames_to_send=[InputAudioRawFrame(audio=LOUD, sample_rate=16000, num_channels=1)],
        expected_down_frames=[InputAudioRawFrame],
    )
    return down[0].audio


async def test_open_gate_passes_audio():
    g = MicGate(open_=True)
    assert await _through(g) == LOUD


async def test_closed_gate_sends_silence_of_same_length():
    g = MicGate(open_=False)
    out = await _through(g)
    assert out == bytes(len(LOUD))


async def test_gate_can_be_reopened():
    g = MicGate(open_=False)
    g.set_open(True)
    assert await _through(g) == LOUD
