"""Ctrl+Shift+Space is a walkie-talkie. Stdlib only.

- Hold Space (with Ctrl+Shift down): you talk. Let go: Rum answers. That's all the key does.
- Holding while Rum talks stops her, and it's your turn.
- A quick tap while Rum is closed does nothing, so she never opens by accident.
- A quick tap while Rum is open closes her (saying "bye", silence or the bar also close her).
- Hands-free (no key at all) is the bar orb / panel switch: toggle().

Modes: closed · hold (mic on only while the key is down) · hands_free (mic always on).
Actions for the daemon: start, stop, interrupt, mic_open, mic_close, hold_start, hold_end.
The daemon calls tick() TAP_SECS after a press, to start Rum once a press from closed is a hold.
"""

from __future__ import annotations

TAP_SECS = 0.3  # held longer than this while closed: open Rum for your turn


class PushToTalk:
    def __init__(self) -> None:
        self.mode = "closed"
        self._down_at: float | None = None
        self._holding = False

    def press(self, now: float, open_: bool, speaking: bool) -> list[str]:
        if not open_:
            self.mode = "closed"
        self._down_at, self._holding = now, False
        if self.mode == "closed":
            return []  # wait: a quick tap shouldn't open Rum (tick() decides)
        self._holding = True
        return (["interrupt"] if speaking else []) + ["hold_start", "mic_open"]

    def tick(self, now: float) -> list[str]:
        """Still down after TAP_SECS while closed: open Rum for this turn."""
        if self._down_at is None or self._holding or now - self._down_at < TAP_SECS:
            return []
        self._holding = True
        self.mode = "hold"
        return ["mic_open", "start", "hold_start"]

    def release(self, now: float) -> list[str]:
        if self._down_at is None:
            return []
        down_at = self._down_at
        early = self.tick(now)  # a hold the daemon's timer hasn't seen yet
        held = self._holding
        self._down_at, self._holding = None, False
        if not held:
            return early  # a quick tap while closed: nothing
        if not early and now - down_at < TAP_SECS:  # a quick tap while open: close Rum
            self.mode = "closed"
            return ["hold_end", "stop"]
        return early + ["hold_end"] + (["mic_close"] if self.mode == "hold" else [])

    def toggle(self, open_: bool) -> list[str]:
        """The bar orb and panel switch: hands-free on, or close."""
        self._down_at, self._holding = None, False
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
