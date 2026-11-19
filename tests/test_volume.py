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


async def test_volume_processor_levels_rums_voice():
    quiet = _speech(-31, seconds=0.6)
    down, _ = await run_test(
        Volume(1.0),
        frames_to_send=[OutputAudioRawFrame(audio=f, sample_rate=24000, num_channels=1) for f in quiet],
        expected_down_frames=[OutputAudioRawFrame] * len(quiet),
    )
    assert _dbfs([f.audio for f in down[10:]])[0] > -24  # well above the -31 it came in at


def _speech(level_dbfs: float, seconds: float = 2.0, rate: int = 24000) -> list[bytes]:
    """A speech-like signal (a tone with syllable pulses) at a given loudness, in 20 ms frames."""
    import math

    amp = 32768 * 10 ** (level_dbfs / 20) * math.sqrt(2)
    n = int(seconds * rate)
    samples = [int(amp * math.sin(2 * math.pi * 220 * i / rate) * (0.6 + 0.4 * abs(math.sin(i / rate * 7))))
               for i in range(n)]
    frame = rate // 50
    return [struct.pack(f"<{len(samples[i:i + frame])}h", *samples[i:i + frame]) for i in range(0, n, frame)]


def _dbfs(frames: list[bytes]) -> tuple[float, int]:
    import math

    s = [x for f in frames for x in struct.unpack(f"<{len(f) // 2}h", f)]
    rms = math.sqrt(sum(x * x for x in s) / len(s))
    return 20 * math.log10(rms / 32768), max(abs(x) for x in s)


def test_leveler_brings_a_quiet_voice_to_speaking_level():
    from omarum.volume import Leveler

    lev = Leveler(volume=1.0)
    out = [lev.process(f) for f in _speech(-31)]  # what ZONOS3 "Willow" measured
    level, peak = _dbfs(out[25:])  # after the first half second
    assert -16 <= level <= -12  # like videos and music (about -14), not quieter
    assert peak < 32767  # no clipping


def test_leveler_never_clips_and_respects_the_volume_slider():
    from omarum.volume import Leveler

    loud = _speech(-6)
    out = [Leveler(volume=3.0).process(f) for f in loud]
    assert _dbfs(out)[1] <= 32000
    quiet_half = [Leveler(volume=0.5).process(f) for f in _speech(-31)]
    assert _dbfs(quiet_half[25:])[0] < _dbfs([Leveler(volume=1.0).process(f) for f in _speech(-31)][25:])[0] - 4


def test_leveler_leaves_silence_alone():
    from omarum.volume import Leveler

    lev = Leveler(volume=1.0)
    hiss = struct.pack("<480h", *([30, -30] * 240))  # about -60 dBFS
    assert lev.process(hiss) == hiss
