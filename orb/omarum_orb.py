"""Rum's orb: a click-through GTK4 layer-shell overlay drawn from daemon events.

Runs on the system Python (PyGObject + gtk4-layer-shell). Launch it through
bin/omarum-orb, which preloads libgtk4-layer-shell before GTK starts.
Style, position, size and colors come from ~/.config/omarum/config.toml and are
re-read whenever the daemon broadcasts {"type": "reload"} (`omarum reload`,
or the Omarchy theme-set hook).
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
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

from omarum.config import load_config  # noqa: E402
from omarum.ipc import SOCKET_PATH, decode, encode  # noqa: E402
from omarum.orbplace import anchors, clamp_size, dims_screen, normalize_position  # noqa: E402
from omarum.orbshapes import glow_layers, line_paths, normalize_style, ring_points  # noqa: E402
from omarum.orbstate import companion_target, display_state, follow_energy  # noqa: E402
from omarum.theme import palette_for, state_color  # noqa: E402

VISIBLE = {"listening", "user_speaking", "thinking", "speaking", "error"}
ERROR_SECS = 3.0
DIM_ALPHA = 0.25


def lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class Orb:
    def __init__(self) -> None:
        self.state = "idle"
        self.alpha = 0.0
        self.level_target = 0.0
        self.user_level = 0.0
        self.companion_level = 0.0
        self.companion_at = 0.0  # when the last real companion level arrived
        self.energy = 0.0
        self.error_since = 0.0
        self.t0 = time.monotonic()
        self.on_reload = lambda: None
        self.load_settings()
        self.color = self.palette["idle"]

    def load_settings(self) -> None:
        cfg = load_config()
        self.style = normalize_style(cfg.orb_style)
        self.position = normalize_position(cfg.orb_position)
        self.size = clamp_size(cfg.orb_size)
        self.palette = palette_for(cfg.orb_colors)

    # -- events (main thread) --------------------------------------------------
    def on_event(self, msg: dict) -> bool:
        kind = msg.get("type")
        if kind == "reload":
            self.load_settings()
            self.on_reload()
        elif kind == "state" or "ok" in msg:
            self.state = msg.get("state", "idle")
            if self.state == "error":
                self.error_since = time.monotonic()
        elif kind == "level":
            value = float(msg.get("value", 0))
            if msg.get("who") == "user" and self.state in ("user_speaking", "listening"):
                self.user_level = max(self.user_level, value)
                self.level_target = max(self.level_target, value)
            elif msg.get("who") == "companion":
                self.companion_level = value  # measured right after playback: in step with the words
                self.companion_at = time.monotonic()
        return False  # one-shot GLib.idle_add

    # -- animation -------------------------------------------------------------
    def tick(self) -> None:
        now = time.monotonic()
        error_done = self.state == "error" and now - self.error_since > ERROR_SECS
        target_alpha = 1.0 if self.state in VISIBLE and not error_done else 0.0
        step = 1 / 12  # ~200 ms fade at 60 fps
        if target_alpha > self.alpha:
            self.alpha = min(target_alpha, self.alpha + step)
        else:
            self.alpha = max(target_alpha, self.alpha - step)
        shown = display_state(self.state, self.user_level)
        self.color = lerp(self.color, state_color(shown, self.palette), 0.12)
        if self.state == "speaking":
            target = companion_target(self.companion_level, now - self.companion_at, now - self.t0)
            self.level_target = max(self.level_target, target)
            self.companion_level *= 0.7  # a level is only "now" for a frame or two
        self.energy = follow_energy(self.energy, self.level_target)
        self.level_target *= 0.82
        self.user_level *= 0.94

    def _alpha_now(self, t: float) -> float:
        alpha = self.alpha
        if self.state == "error":
            alpha *= 0.6 + 0.4 * math.sin(t * 2 * math.pi)
        return alpha

    def draw(self, cr: cairo.Context, w: int, h: int) -> None:
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if self.alpha <= 0.001:
            return
        t = time.monotonic() - self.t0
        alpha = self._alpha_now(t)
        size = min(w, h)
        cr.translate((w - size) / 2, (h - size) / 2)
        r, g, b = self.color
        c = size / 2

        halo = cairo.RadialGradient(c, c, size * 0.15, c, c, size * 0.47)
        halo.add_color_stop_rgba(0, r, g, b, 0.18 * alpha)
        halo.add_color_stop_rgba(1, r, g, b, 0)
        cr.set_source(halo)
        cr.arc(c, c, size * 0.47, 0, 2 * math.pi)
        cr.fill()

        if self.style == "lines":
            self._draw_lines(cr, t, size, alpha)
        elif self.style == "ring":
            self._draw_ring(cr, t, size, alpha)
        else:
            self._draw_glow(cr, t, size, alpha)

    def _path(self, cr, points, close: bool) -> None:
        cr.new_path()
        x, y = points[0]
        cr.move_to(x, y)
        for x, y in points[1:]:
            cr.line_to(x, y)
        if close:
            cr.close_path()

    def _draw_glow(self, cr, t, size, alpha) -> None:
        r, g, b = self.color
        c = size / 2
        breathe = 0.9 + 0.05 * math.sin(t * 3) if self.state == "thinking" else 1.0
        layers = glow_layers(t, self.energy, size, breathe)
        for i, pts in enumerate(layers):  # outermost first
            layer = 3 - i
            rb = max(math.hypot(x - c, y - c) for x, y in pts)
            self._path(cr, pts, close=True)
            grad = cairo.RadialGradient(c, c - size * 0.04, 3, c, c, rb * 1.2)
            grad.add_color_stop_rgba(0, r, g, b, (0.6 - layer * 0.1) * alpha)
            grad.add_color_stop_rgba(1, r, g, b, 0.04 * alpha)
            cr.set_source(grad)
            cr.fill()

    def _draw_lines(self, cr, t, size, alpha) -> None:
        r, g, b = self.color
        c = size / 2
        cr.save()
        cr.arc(c, c, size * 0.42, 0, 2 * math.pi)
        cr.set_source_rgba(r, g, b, 0.22 * alpha)
        cr.set_line_width(1.2)
        cr.stroke_preserve()
        cr.clip()
        for k, pts in enumerate(line_paths(t, self.energy, size)):
            self._path(cr, pts, close=False)
            middle = k == 2
            cr.set_source_rgba(r, g, b, (0.9 if middle else 0.45) * alpha)
            cr.set_line_width(2.2 if middle else 1.3)
            cr.stroke()
        cr.restore()

    def _draw_ring(self, cr, t, size, alpha) -> None:
        r, g, b = self.color
        c = size / 2
        pts = ring_points(t, self.energy, size)
        self._path(cr, pts, close=True)
        cr.set_source_rgba(r, g, b, 0.9 * alpha)
        cr.set_line_width(2.0)
        cr.stroke()
        cr.arc(c, c, 3 + self.energy * 3, 0, 2 * math.pi)
        cr.set_source_rgba(r, g, b, 0.7 * alpha)
        cr.fill()


def socket_reader(orb: Orb) -> None:
    """Background thread: follow daemon events; reconnect every second."""
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.connect(str(SOCKET_PATH))
                s.sendall(encode({"cmd": "status"}))
                GLib.idle_add(orb.on_event, {"type": "reload"})  # daemon may have restarted with new settings
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


def _click_through(win: Gtk.Window) -> None:
    win.connect("realize", lambda _w: win.get_surface().set_input_region(cairo.Region()))


def _transparent(display) -> None:
    css = Gtk.CssProvider()
    css.load_from_string("window { background: transparent; }")
    Gtk.StyleContext.add_provider_for_display(display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def _place(win: Gtk.Window, area: Gtk.DrawingArea, orb: Orb) -> None:
    a = anchors(orb.position)
    for name, edge in (("top", LayerShell.Edge.TOP), ("bottom", LayerShell.Edge.BOTTOM),
                       ("left", LayerShell.Edge.LEFT), ("right", LayerShell.Edge.RIGHT)):
        LayerShell.set_anchor(win, edge, a[name])
        LayerShell.set_margin(win, edge, a["margin"] if a[name] else 0)
    area.set_content_width(orb.size)
    area.set_content_height(orb.size)
    win.set_default_size(orb.size, orb.size)


def on_activate(app: Gtk.Application, orb: Orb) -> None:
    _transparent(Gdk.Display.get_default())

    # Optional full-screen dim behind a centered orb.
    dim = Gtk.Window(application=app)
    LayerShell.init_for_window(dim)
    LayerShell.set_namespace(dim, "omarum-dim")
    LayerShell.set_layer(dim, LayerShell.Layer.TOP)
    for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
        LayerShell.set_anchor(dim, edge, True)
    LayerShell.set_keyboard_mode(dim, LayerShell.KeyboardMode.NONE)
    LayerShell.set_exclusive_zone(dim, -1)
    dim_area = Gtk.DrawingArea()

    def draw_dim(_a, cr, _w, _h):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        a = DIM_ALPHA * orb.alpha if dims_screen(orb.position) else 0.0
        cr.set_source_rgba(0, 0, 0, a)
        cr.paint()

    dim_area.set_draw_func(draw_dim)
    dim.set_child(dim_area)
    _click_through(dim)
    dim.present()

    win = Gtk.Window(application=app)
    win.set_decorated(False)
    LayerShell.init_for_window(win)
    LayerShell.set_namespace(win, "omarum-orb")
    LayerShell.set_layer(win, LayerShell.Layer.OVERLAY)
    LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.NONE)
    LayerShell.set_exclusive_zone(win, 0)
    area = Gtk.DrawingArea()
    area.set_draw_func(lambda _a, cr, w, h: orb.draw(cr, w, h))
    win.set_child(area)
    _place(win, area, orb)
    orb.on_reload = lambda: _place(win, area, orb)

    def tick(widget, _clock):
        orb.tick()
        widget.queue_draw()
        if dims_screen(orb.position) or orb.alpha > 0:
            dim_area.queue_draw()
        return GLib.SOURCE_CONTINUE

    area.add_tick_callback(tick)
    _click_through(win)
    win.present()

    threading.Thread(target=socket_reader, args=(orb,), daemon=True).start()


def main() -> None:
    orb = Orb()
    app = Gtk.Application(application_id="org.omarchy.omarum.orb")
    app.connect("activate", on_activate, orb)
    app.run([])


if __name__ == "__main__":
    main()
