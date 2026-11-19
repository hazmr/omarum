"""One shortcut, Ctrl+Shift+Space (Ctrl+Shift stay down; only Space is timed). Stdlib only.

- Space tap tap (two taps close together): open the conversation (hands-free), or close it.
- Space held: your turn. Rum waits however long you pause and answers when you let go.
  From closed it opens a conversation where the mic is on only while you hold.
- Space tap: stop Rum talking, instantly (it acts on the press; nothing waits for a second tap).
  While closed a single tap does nothing, so it never opens by accident.

Modes: closed · hold (mic only while held) · hands_free (mic always on).
Actions for the daemon: start, stop, interrupt, mic_open, mic_close, hold_start, hold_end.
The daemon calls tick() TAP_SECS after a press, to notice a hold while the key is still down.
"""

from __future__ import annotations

TAP_SECS = 0.3      # a press shorter than this is a tap; longer is a hold
DOUBLE_SECS = 0.45  # a second tap this soon after the first one's release makes a double tap


class PushToTalk:
    def __init__(self) -> None:
        self.mode = "closed"
        self._down_at: float | None = None
        self._holding = False
        self._double = False
        self._last_tap_at: float | None = None

    def press(self, now: float, open_: bool, speaking: bool) -> list[str]:
        if not open_:
            self.mode = "closed"
        self._down_at, self._holding, self._double = now, False, False
        actions = ["interrupt"] if speaking else []
        if self._last_tap_at is not None and now - self._last_tap_at <= DOUBLE_SECS:
            self._last_tap_at, self._double = None, True
            if self.mode == "closed":
                self.mode = "hands_free"
                return actions + ["mic_open", "start"]
            self.mode = "closed"
            return actions + ["stop"]
        if self.mode != "closed":
            actions += ["hold_start", "mic_open"]  # Rum waits while the key is down (a tap ends it at once)
        return actions

    def tick(self, now: float) -> list[str]:
        """Still down after TAP_SECS: it's a hold."""
        if self._down_at is None or self._holding or self._double or now - self._down_at < TAP_SECS:
            return []
        self._holding = True
        if self.mode == "closed":
            self.mode = "hold"
            return ["mic_open", "start", "hold_start"]
        return []

    def release(self, now: float) -> list[str]:
        if self._down_at is None:
            return []
        early = self.tick(now)  # a hold the daemon's timer hasn't seen yet
        tap = not self._holding
        self._down_at = None
        if self._double:
            return early
        if tap:
            self._last_tap_at = now
            if self.mode == "closed":
                return early
        else:
            self._last_tap_at = None
        return early + ["hold_end"] + (["mic_close"] if self.mode == "hold" else [])

    def toggle(self, open_: bool) -> list[str]:
        """The bar button and panel switch: hands-free on, or close."""
        self._down_at, self._last_tap_at = None, None
        if open_:
            self.mode = "closed"
            return ["stop"]
        self.mode = "hands_free"
        return ["mic_open", "start"]

    def closed(self) -> None:
        """The conversation ended some other way (silence timeout, error)."""
        self.mode = "closed"
        self._down_at = None
        self._holding = self._double = False
