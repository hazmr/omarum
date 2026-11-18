"""Rum's orb: a click-through GTK4 layer-shell overlay drawn from daemon events.

Runs on the system Python (PyGObject + gtk4-layer-shell). Launch it through
bin/omarum-orb, which preloads libgtk4-layer-shell before GTK starts.
"""

from __future__ import annotations

import math
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from omarum.ipc import SOCKET_PATH, decode, encode  # noqa: E402
from omarum.theme import load_palette, state_color  # noqa: E402

SIZE = 160
MARGIN = 16
VISIBLE = {"listening", "user_speaking", "thinking", "speaking", "error"}
ERROR_SECS = 3.0


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class Orb:
    def __init__(self) -> None:
        self.palette = load_palette()
        self.state = "idle"
        self.color = self.palette["idle"]
        self.alpha = 0.0
        self.level_target = 0.0
        self.energy = 0.0
        self.error_since = 0.0
        self.t0 = time.monotonic()

    # -- events (main thread) --------------------------------------------------
    def on_event(self, msg: dict) -> bool:
        if msg.get("type") == "state" or "ok" in msg:
            self.state = msg.get("state", "idle")
            if self.state == "error":
                self.error_since = time.monotonic()
        elif msg.get("type") == "level":
            who = msg.get("who")
            if (who == "user" and self.state in ("user_speaking", "listening")) or (
                who == "companion" and self.state == "speaking"
            ):
                self.level_target = max(self.level_target, float(msg.get("value", 0)))
        return False  # one-shot GLib.idle_add

    def reload_theme(self) -> None:
        self.palette = load_palette()

    # -- animation -------------------------------------------------------------
    def tick(self) -> None:
        now = time.monotonic()
        error_done = self.state == "error" and now - self.error_since > ERROR_SECS
        target_alpha = 1.0 if self.state in VISIBLE and not error_done else 0.0
        step = 1 / 12  # ~200 ms fade at 60 fps
        self.alpha = min(target_alpha, self.alpha + step) if target_alpha > self.alpha else max(target_alpha, self.alpha - step)
        self.color = lerp(self.color, state_color(self.state, self.palette), 0.07)
        self.energy += (self.level_target - self.energy) * 0.15
        self.level_target *= 0.9

    def draw(self, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.alpha <= 0.001:
            return
        t = time.monotonic() - self.t0
        c = w / 2
        e = self.energy
        base = SIZE * 0.29
        breathe = 1 + 0.04 * math.sin(t * 1.3)
        if self.state == "thinking":
            breathe *= 0.9 + 0.05 * math.sin(t * 3)
        alpha = self.alpha
        if self.state == "error":
            alpha *= 0.6 + 0.4 * math.sin(t * 2 * math.pi)
        r, g, b = self.color

        # soft outer halo
        halo = cairo.RadialGradient(c, c, base * 0.5, c, c, base * 1.6)
        halo.add_color_stop_rgba(0, r, g, b, 0.18 * alpha)
        halo.add_color_stop_rgba(1, r, g, b, 0)
        cr.set_source(halo)
        cr.arc(c, c, base * 1.6, 0, 2 * math.pi)
        cr.fill()

        for layer in range(3, -1, -1):
            rb = base * (0.55 + layer * 0.12) * breathe + e * 8
            cr.new_path()
            for i in range(91):
                a = i / 90 * 2 * math.pi
                wob = (
                    math.sin(a * 3 + t * 1.7 + layer) * 0.5
                    + math.sin(a * 5 - t * 2.3 + layer * 2) * 0.35
                    + math.sin(a * 2 + t * 0.8) * 0.4
                )
                rr = rb + wob * (2 + e * 10) * (1 + layer * 0.3)
                x, y = c + math.cos(a) * rr, c + math.sin(a) * rr
                cr.move_to(x, y) if i == 0 else cr.line_to(x, y)
            cr.close_path()
            grad = cairo.RadialGradient(c, c - 6, 3, c, c, rb * 1.2)
            grad.add_color_stop_rgba(0, r, g, b, (0.6 - layer * 0.1) * alpha)
            grad.add_color_stop_rgba(1, r, g, b, 0.04 * alpha)
            cr.set_source(grad)
            cr.fill()


def socket_reader(orb: Orb) -> None:
    """Background thread: follow daemon events; reconnect every second."""
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(SOCKET_PATH))
                s.sendall(encode({"cmd": "status"}))
                with s.makefile("rb") as f:
                    for line in f:
                        try:
                            GLib.idle_add(orb.on_event, decode(line))
                        except ValueError:
                            continue
        except OSError:
            pass
        GLib.idle_add(orb.on_event, {"type": "state", "state": "closed"})
        time.sleep(1)


def on_activate(app: Gtk.Application, orb: Orb) -> None:
    win = Gtk.Window(application=app)
    win.set_default_size(SIZE, SIZE)
    win.set_decorated(False)

    LayerShell.init_for_window(win)
    LayerShell.set_namespace(win, "omarum-orb")
    LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
    LayerShell.set_anchor(win, LayerShell.Edge.TOP, True)
    LayerShell.set_anchor(win, LayerShell.Edge.RIGHT, True)
    LayerShell.set_margin(win, LayerShell.Edge.TOP, MARGIN)
    LayerShell.set_margin(win, LayerShell.Edge.RIGHT, MARGIN)
    LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
    LayerShell.set_exclusive_zone(win, 0)

    css = Gtk.CssProvider()
    css.load_from_string("window { background: transparent; }")
    Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    area = Gtk.DrawingArea()
    area.set_content_width(SIZE)
    area.set_content_height(SIZE)
    area.set_draw_func(lambda _a, cr, w, h: orb.draw(cr, w, h))
    win.set_child(area)

    def tick(widget, _clock):
        orb.tick()
        widget.queue_draw()
        return GLib.SOURCE_CONTINUE

    area.add_tick_callback(tick)

    def click_through(_w):
        win.get_surface().set_input_region(cairo.Region())

    win.connect("realize", click_through)
    win.present()

    threading.Thread(target=socket_reader, args=(orb,), daemon=True).start()


def main() -> None:
    orb = Orb()
    app = Gtk.Application(application_id="org.omarchy.omarum.orb")
    app.connect("activate", on_activate, orb)
    app.run([])


if __name__ == "__main__":
    main()
