"""Ctrl+Shift+Space. Stdlib only. Ctrl+Shift can stay down the whole time; only Space is timed.

- Double tap Space: open Rum if she's closed, close her in any other state (starting,
  listening, thinking, talking).
- Hold Space: you talk; let go and Rum answers. Holding while Rum talks stops her.
- A single tap only stops Rum if she's talking; it never opens or closes.
- What a double tap opens follows Talk mode (settings): Push to talk (default) opens with the mic
  off, so it hears you only while Space is held; Hands-free opens with the mic always on.
  The bar orb / panel switch always means hands-free: toggle().

Hyprland quirks this handles (seen in daemon.log): every release of Space arrives as an extra
"down" plus the "up", and a very quick tap may arrive only as that pair. So taps are counted on
release, and a "down" while already down is ignored.

Modes: closed · hold (mic on only while the key is down) · hands_free (mic always on).
Actions for the daemon: start, stop, interrupt, mic_open, mic_close, hold_start, hold_end.
The daemon calls tick() TAP_SECS after a press, to start Rum once a press from closed is a hold.
"""

from __future__ import annotations

TAP_SECS = 0.3  # down shorter than this: a tap; longer while closed: open Rum for your turn
DOUBLE_SECS = 0.6  # two taps (release to release) within this: open / close


class PushToTalk:
    def __init__(self) -> None:
        self.mode = "closed"
        self.talk_mode = "push_to_talk"  # or "hands_free"; the daemon keeps it in step with the config
        self._down_at: float | None = None
        self._holding = False
        self._last_tap: float | None = None

    def press(self, now: float, open_: bool, speaking: bool) -> list[str]:
        if self._down_at is not None:
            return []  # already down: Hyprland sends a second "down" together with the release
        if not open_:
            self.mode = "closed"
        elif self.mode == "closed":
            self.mode = "hold"  # Rum is open but we thought closed: resync
        self._down_at, self._holding = now, False
        if self.mode == "closed":
            return []  # wait: a tap shouldn't open Rum (tick() decides on a hold)
        self._holding = True
        return (["interrupt"] if speaking else []) + ["hold_start", "mic_open"]

    def tick(self, now: float) -> list[str]:
        """Still down after TAP_SECS while closed: open Rum for this turn."""
        if self._down_at is None or self._holding or now - self._down_at < TAP_SECS:
            return []
        self._holding = True
        self._last_tap = None
        self.mode = "hold"
        return ["mic_open", "start", "hold_start"]

    def release(self, now: float) -> list[str]:
        if self._down_at is None:
            return []
        down_at = self._down_at
        early = self.tick(now)  # a hold the daemon's timer hasn't seen yet
        held = self._holding
        self._down_at, self._holding = None, False
        actions = early + (["hold_end"] if held else [])
        if held and self.mode == "hold":
            actions.append("mic_close")
        if early or now - down_at >= TAP_SECS:
            self._last_tap = None  # a hold, not a tap
            return actions
        # A tap. Two in a row: open or close.
        if self._last_tap is None or now - self._last_tap > DOUBLE_SECS:
            self._last_tap = now
            return actions
        self._last_tap = None
        if self.mode == "closed":
            if self.talk_mode == "hands_free":
                self.mode = "hands_free"
                return actions + ["mic_open", "start"]
            self.mode = "hold"  # push to talk: open with the mic off; holding Space turns it on
            return actions + ["mic_close", "start"]
        self.mode = "closed"
        return actions + ["stop"]

    def toggle(self, open_: bool) -> list[str]:
        """The bar orb and panel switch: hands-free on, or close."""
        self._down_at, self._holding, self._last_tap = None, False, None
        if open_:
            self.mode = "closed"
            return ["stop"]
        self.mode = "hands_free"
        return ["mic_open", "start"]

    def closed(self) -> None:
        """The conversation ended some other way (silence timeout, error, the bar)."""
        self.mode = "closed"
        self._down_at = None
        self._holding = False
        self._last_tap = None
