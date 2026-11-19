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
    assert -18 <= level <= -14  # loud for laptop speakers, with room left for peaks
    assert peak < 32767  # no clipping


def test_leveler_never_clips_and_respects_the_volume_slider():
    from omarum.volume import Leveler

    def run(frames, volume):  # one leveler follows one voice, frame after frame
        lev = Leveler(volume=volume)
        return [lev.process(f) for f in frames]

    assert _dbfs(run(_speech(-6), 3.0))[1] <= 32000
    assert _dbfs(run(_speech(-31), 0.5)[25:])[0] < _dbfs(run(_speech(-31), 1.0)[25:])[0] - 4


def test_leveler_leaves_silence_alone():
    from omarum.volume import Leveler

    lev = Leveler(volume=1.0)
    hiss = struct.pack("<480h", *([30, -30] * 240))  # about -60 dBFS
    assert lev.process(hiss) == hiss


def _peaky(seconds: float = 2.0, rate: int = 16000) -> list[bytes]:
    """Loud, peaky speech like ElevenLabs Jessica: about -20 dB average with -2 dB peaks."""
    import math

    n = int(seconds * rate)
    s = []
    for i in range(n):
        t = i / rate
        burst = 1.0 if (t * 6) % 1 < 0.08 else 0.25          # a loud syllable start, six times a second
        s.append(int(26000 * burst * math.sin(2 * math.pi * 180 * t) * (0.5 + 0.5 * abs(math.sin(t * 9)))))
    frame = rate // 50
    return [struct.pack(f"<{len(s[i:i + frame])}h", *s[i:i + frame]) for i in range(0, n, frame)]


def test_leveler_never_hits_the_ceiling_on_a_loud_peaky_voice():
    from omarum.volume import Leveler

    for volume in (1.0, 1.5, 3.0):
        lev = Leveler(volume=volume)
        out = [lev.process(f) for f in _peaky()]
        samples = [x for f in out for x in struct.unpack(f"<{len(f) // 2}h", f)]
        assert sum(1 for x in samples if abs(x) >= 32000) == 0, volume  # no crackle


def test_leveler_changes_volume_smoothly():
    from omarum.volume import Leveler

    lev = Leveler(volume=1.0)
    frames = _peaky()
    gains = []
    for f in frames:
        lev.process(f)
        gains.append(lev.gain)
    # From one 20 ms slice to the next, the volume rises gently (at most +15 %).
    assert all(b <= a * 1.15 + 1e-9 for a, b in zip(gains, gains[1:]))
