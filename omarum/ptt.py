"""One shortcut for everything: hold to talk (and interrupt), tap for hands-free. Stdlib only.

Modes: closed · hold (mic open only while the key is down) · hands_free (mic always open).
Actions returned for the daemon: start, stop, interrupt, mic_open, mic_close, hands_free.
"""

from __future__ import annotations

TAP_SECS = 0.3  # shorter than this is a tap, longer is a hold


class PushToTalk:
    def __init__(self) -> None:
        self.mode = "closed"
        self._down_at: float | None = None
        self._was_mode = "closed"

    def press(self, now: float, open_: bool, speaking: bool) -> list[str]:
        if not open_:
            self.mode = "closed"
        self._down_at, self._was_mode = now, self.mode
        if self.mode == "closed":
            self.mode = "hold"
            return ["start", "mic_open"]
        actions = ["interrupt"] if speaking else []
        if self.mode == "hold":
            actions.append("mic_open")
        return actions

    def release(self, now: float) -> list[str]:
        if self._down_at is None:
            return []
        tap = now - self._down_at < TAP_SECS
        self._down_at = None
        if self._was_mode == "hands_free":
            if tap:
                self.mode = "closed"
                return ["stop"]
            return []  # held while hands-free: the mic stays open
        if tap:
            self.mode = "hands_free"
            return ["hands_free"]
        self.mode = "hold"
        return ["mic_close"]

    def closed(self) -> None:
        """The session ended some other way (silence timeout, error, old toggle)."""
        self.mode = "closed"
        self._down_at = None
