import struct

from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.tests.utils import run_test

from omarum.volume import Volume, scale_pcm16


def test_scale_raises_and_clips():
    pcm = struct.pack("<3h", 1000, -1000, 30000)
    assert struct.unpack("<3h", scale_pcm16(pcm, 1.5)) == (1500, -1500, 32767)


def test_scale_unity_is_unchanged():
    pcm = struct.pack("<2h", 123, -456)
    assert scale_pcm16(pcm, 1.0) == pcm


async def test_volume_processor_scales_output_audio():
    pcm = struct.pack("<2h", 1000, -1000)
    down, _ = await run_test(
        Volume(2.0),
        frames_to_send=[OutputAudioRawFrame(audio=pcm, sample_rate=24000, num_channels=1)],
        expected_down_frames=[OutputAudioRawFrame],
    )
    assert struct.unpack("<2h", down[0].audio) == (2000, -2000)
