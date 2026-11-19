# Phase 1 (prototype) report

**Question the prototype had to answer:** can a voice-only companion on an Omarchy laptop feel fast and natural enough to be worth building in full?

**Answer: yes**, with the caveats below.

## What was built

- Press **Super + H** → orb appears → talk → Rum answers out loud. Toggle again or 8 s of silence ends it.
- Ears: Whisper (large-v3-turbo on an NVIDIA GPU, base.en on CPU).
- Brain: the user's own `claude` CLI on their subscription (one persistent stream-json process).
- Voice: user-chosen, failing over **ElevenLabs → ZONOS3-Mini → Kokoro**.
- Orb: GTK4 layer-shell overlay, theme colors made vivid, driven by live mic level and real playback.

## Measurements (Ryzen 7 6800H, Radeon 680M, NVIDIA GPU unavailable during testing)

| Step | Time |
|---|---|
| End of speech → end-of-turn decision | 0.3 s (+ smart-turn check) |
| Whisper base.en on CPU | ~0.3–0.6 s |
| Claude (Haiku) first words, warm process | 0.7–1.3 s (one outlier 4.4 s) |
| ZONOS3-Mini first sound (Vulkan on Radeon) | ~0.41 s, lead-in silence trimmed |
| **End of speech → Rum's first sound** | **~1.7–2.2 s** |

The original target was 1.5 s. The brain is now the biggest piece and is outside our control on the subscription path; a GPU for Whisper would cut a further ~0.3–0.5 s.

## What we learned (and fixed)

- **Noise interrupted Rum** (breaths and clicks turned into "Okay." / "Bye."). Turns now start only from transcribed words, with stricter VAD.
- **Rum heard itself** through the laptop speakers. The mic is muted while Rum speaks. Proper fix: PipeWire WebRTC echo cancellation, which also stops background videos being heard (not yet enabled).
- **Closing didn't stop speech** (EndFrame waited for queued audio). Sessions are now cancelled and stale events dropped.
- **Piper sounded robotic.** Kokoro was better; ZONOS3-Mini was better still and runs on the iGPU.
- **The orb looked gray.** The turn signal arrived after speech and the "speaking" signal never crossed the voice switcher; pastel theme colors read as gray. It now uses the live mic level, real playback, and boosted colors.
- **ALSA segfault** when a session reopened audio while a write thread from the last one was still running. Fixed with a 0.6 s release cooldown; the daemon also auto-restarts.
- **Claude Code loaded the user's own hooks/plugins** into the companion. It now runs with `--setting-sources ""`.

## Open items carried into later phases

- Echo cancellation (would restore barge-in and ignore other audio).
- Config validation; a systemd user unit instead of the shell restart loop (phase 5).
- Owner's final voice pick (default: ZONOS3 "Savannah").
