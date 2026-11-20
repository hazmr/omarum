import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland
import qs.Commons
import qs.Commons as Commons

// Rum's orb, drawn by the plugin (ported from the old GTK orb: orb/omarum_orb.py,
// omarum/orbshapes.py, omarum/orbstate.py). It exists only while it shows: when it
// fades out, its window goes away, so a closed Rum leaves nothing on screen.
Scope {
  id: orb

  required property var engine

  readonly property var cfg: engine.info.orb || ({ style: "glow", position: "top-right", size: 160 })
  readonly property string style: ["glow", "lines", "ring"].indexOf(cfg.style) >= 0 ? cfg.style : "glow"
  readonly property string position: ["top-right", "top-center", "top-left", "center", "bottom-center"].indexOf(cfg.position) >= 0 ? cfg.position : "top-right"
  readonly property int size: Math.max(96, Math.min(320, Number(cfg.size) || 160))
  // The palette arrives as "#rrggbb" text; turn it into real colors once. Mixing text
  // in mix() gave NaN channels, which drew Rum's and your color as black.
  readonly property var hex: engine.info.colors || ({ user: "#cc8979", companion: "#82c9ed", idle: "#584e51", error: "#ee7350" })
  readonly property var colors: ({
    user: Qt.color(hex.user || "#cc8979"), companion: Qt.color(hex.companion || "#82c9ed"),
    idle: Qt.color(hex.idle || "#584e51"), error: Qt.color(hex.error || "#ee7350")
  })
  readonly property var visibleStates: ["starting", "listening", "user_speaking", "thinking", "speaking", "error"]
  readonly property real voiceThreshold: 0.25  // omarum.orbstate.USER_VOICE_THRESHOLD

  // Animation state, advanced by the frame timer.
  property real alpha: 0
  property real energy: 0
  property real levelTarget: 0
  property real userLevel: 0
  property real companionLevel: 0
  property real companionAt: -10
  property real errorSince: 0
  property real t: 0
  property color color: restColor

  readonly property bool shown: alpha > 0.001

  function shownState() {
    var s = engine.state
    if ((s === "listening" || s === "user_speaking") && userLevel >= voiceThreshold) return "user_speaking"
    return s
  }
  // Listening / thinking: Rum's color, softened toward the theme's text color so it reads
  // as calm but stays clearly visible (the theme's "muted" color is nearly black on dark themes).
  readonly property color restColor: mix(colors.companion, Commons.Color.foreground, 0.35)
  function targetColor(s) {
    if (s === "user_speaking") return colors.user
    if (s === "speaking") return colors.companion
    if (s === "error") return colors.error
    return restColor
  }
  function speakingEnergy(t) {
    var syl = Math.abs(Math.sin(t * 7.3)) * Math.abs(Math.sin(t * 2.1))
    var words = 0.5 + 0.5 * Math.sin(t * 0.9)
    return Math.min(1, (0.25 + syl * 0.9) * (0.4 + 0.6 * words))
  }
  function mix(a, b, k) { return Qt.rgba(a.r + (b.r - a.r) * k, a.g + (b.g - a.g) * k, a.b + (b.b - a.b) * k, 1) }

  Connections {
    target: orb.engine
    function onLevel(who, value) {
      if (who === "user" && (orb.engine.state === "user_speaking" || orb.engine.state === "listening")) {
        orb.userLevel = Math.max(orb.userLevel, value)
        orb.levelTarget = Math.max(orb.levelTarget, value)
      } else if (who === "companion") {
        orb.companionLevel = value
        orb.companionAt = orb.t
      }
    }
    function onStateChanged() { if (orb.engine.state === "error") orb.errorSince = orb.t }
  }

  // ~60 fps while there is anything to draw or fade in; idle costs nothing.
  Timer {
    interval: 16
    repeat: true
    running: orb.shown || orb.visibleStates.indexOf(orb.engine.state) >= 0
    onTriggered: {
      orb.t += 0.016
      var errorDone = orb.engine.state === "error" && orb.t - orb.errorSince > 3
      var target = orb.visibleStates.indexOf(orb.engine.state) >= 0 && !errorDone ? 1 : 0
      var step = Style.duration(100) > 0 ? 1 / 12 : 1
      orb.alpha = target > orb.alpha ? Math.min(target, orb.alpha + step) : Math.max(target, orb.alpha - step)
      orb.color = orb.mix(orb.color, orb.targetColor(orb.shownState()), 0.12)
      if (orb.engine.state === "speaking") {
        var since = orb.t - orb.companionAt
        var goal = since > 1 ? orb.speakingEnergy(orb.t) * 0.6 : Math.min(1, orb.companionLevel * 2)
        orb.levelTarget = Math.max(orb.levelTarget, goal)
        orb.companionLevel *= 0.7
      }
      var rate = orb.levelTarget > orb.energy ? 0.55 : 0.12
      orb.energy += (orb.levelTarget - orb.energy) * rate
      orb.levelTarget *= 0.82
      orb.userLevel *= 0.94
      if (orbWindow.item) orbWindow.item.paint()
    }
  }

  // A soft dim behind a centered orb (the "focus" position).
  LazyLoader {
    active: orb.shown && orb.position === "center"
    PanelWindow {
      screen: orb.targetScreen()
      anchors { top: true; bottom: true; left: true; right: true }
      color: Qt.rgba(0, 0, 0, 0.25 * orb.alpha)
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.layer: WlrLayer.Top
      WlrLayershell.namespace: "omarum-dim"
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      mask: Region {}
    }
  }

  function targetScreen() {
    var m = Hyprland.focusedMonitor
    for (var i = 0; i < Quickshell.screens.length; i++)
      if (m && Quickshell.screens[i].name === m.name) return Quickshell.screens[i]
    return Quickshell.screens[0]
  }

  LazyLoader {
    id: orbWindow
    active: orb.shown
    PanelWindow {
      id: win
      function paint() { canvas.requestPaint() }
      screen: orb.targetScreen()
      anchors {
        top: orb.position.indexOf("top") === 0
        bottom: orb.position === "bottom-center"
        left: orb.position === "top-left"
        right: orb.position === "top-right"
      }
      margins { top: 16; bottom: 16; left: 16; right: 16 }
      implicitWidth: orb.size
      implicitHeight: orb.size
      color: "transparent"
      exclusionMode: ExclusionMode.Ignore
      WlrLayershell.layer: WlrLayer.Overlay
      WlrLayershell.namespace: "omarum-orb"
      WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
      mask: Region {}  // clicks go through to whatever is underneath

      Canvas {
        id: canvas
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          var size = Math.min(width, height), c = size / 2
          var t = orb.t, e = orb.energy, col = orb.color
          var alpha = orb.alpha * (orb.engine.state === "error" ? 0.6 + 0.4 * Math.sin(t * 2 * Math.PI) : 1)
          function rgba(a) { return Qt.rgba(col.r, col.g, col.b, a) }
          function path(pts, close) {
            ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1])
            for (var i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
            if (close) ctx.closePath()
          }

          var halo = ctx.createRadialGradient(c, c, size * 0.15, c, c, size * 0.47)
          halo.addColorStop(0, rgba(0.18 * alpha)); halo.addColorStop(1, rgba(0))
          ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(c, c, size * 0.47, 0, 2 * Math.PI); ctx.fill()

          if (orb.style === "lines") {
            ctx.save()
            ctx.beginPath(); ctx.arc(c, c, size * 0.42, 0, 2 * Math.PI)
            ctx.strokeStyle = rgba(0.22 * alpha); ctx.lineWidth = 1.2; ctx.stroke(); ctx.clip()
            var radius = size * 0.42, stepX = size / 80
            for (var k = 0; k < 5; k++) {
              var amp = (size * 0.04 + e * size * 0.44) * (1 - Math.abs(k - 2) / 5)
              var freq = 1.6 + k * 0.35, phase = t * (1.2 + k * 0.25) + k, pts = []
              for (var x = -radius; x <= radius + 1e-9; x += stepX) {
                var env = Math.pow(Math.cos(x / radius * Math.PI / 2), 2)
                pts.push([c + x, c + Math.sin(x / radius * Math.PI * freq + phase) * amp * env])
              }
              path(pts, false)
              ctx.strokeStyle = rgba((k === 2 ? 0.9 : 0.45) * alpha); ctx.lineWidth = k === 2 ? 2.2 : 1.3; ctx.stroke()
            }
            ctx.restore()
          } else if (orb.style === "ring") {
            var rr = size * 0.34, ring = []
            for (var i = 0; i <= 180; i++) {
              var a = i / 180 * 2 * Math.PI - Math.PI / 2
              var n = Math.sin(a * 8 + t * 4) * Math.sin(a * 3 - t * 2.2) + 0.5 * Math.sin(a * 13 + t * 6)
              var r = rr + n * (size * 0.01 + e * size * 0.16)
              ring.push([c + Math.cos(a) * r, c + Math.sin(a) * r])
            }
            path(ring, true); ctx.strokeStyle = rgba(0.9 * alpha); ctx.lineWidth = 2; ctx.stroke()
            ctx.beginPath(); ctx.arc(c, c, 3 + e * 3, 0, 2 * Math.PI); ctx.fillStyle = rgba(0.7 * alpha); ctx.fill()
          } else {
            var breathe = orb.engine.state === "thinking" ? 0.9 + 0.05 * Math.sin(t * 3) : 1
            var base = size * 0.29
            for (var layer = 3; layer >= 0; layer--) {
              var rb = base * (0.55 + layer * 0.12) * breathe * (1 + 0.04 * Math.sin(t * 1.3)) + e * size * 0.05
              var blob = [], maxR = 0
              for (var j = 0; j <= 90; j++) {
                var ang = j / 90 * 2 * Math.PI
                var wob = Math.sin(ang * 3 + t * 1.7 + layer) * 0.5 + Math.sin(ang * 5 - t * 2.3 + layer * 2) * 0.35 + Math.sin(ang * 2 + t * 0.8) * 0.4
                var rad = rb + wob * (size * 0.0125 + e * size * 0.0625) * (1 + layer * 0.3)
                maxR = Math.max(maxR, rad)
                blob.push([c + Math.cos(ang) * rad, c + Math.sin(ang) * rad])
              }
              path(blob, true)
              var g = ctx.createRadialGradient(c, c - size * 0.04, 3, c, c, maxR * 1.2)
              g.addColorStop(0, rgba((0.6 - layer * 0.1) * alpha)); g.addColorStop(1, rgba(0.04 * alpha))
              ctx.fillStyle = g; ctx.fill()
            }
          }
        }
      }
    }
  }
}
