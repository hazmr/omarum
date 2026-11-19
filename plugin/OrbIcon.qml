import QtQuick
import qs.Commons

// Rum's breathing glow (the orb's "glow" style), small enough for the bar.
// Static when `live` is false, so a closed Rum costs nothing.
Canvas {
  id: orb

  property color color: "#b59790"
  property bool live: false      // breathing at all
  property real energy: 0        // 0..1, how strongly a voice moves it
  property real t: 0

  implicitWidth: 16
  implicitHeight: 16
  antialiasing: true
  renderStrategy: Canvas.Cooperative

  onColorChanged: requestPaint()
  onLiveChanged: requestPaint()
  onEnergyChanged: requestPaint()
  onWidthChanged: requestPaint()

  Timer {
    // Frames only while alive; with animations off (Style.duration → 0) it stays still.
    interval: 40
    repeat: true
    running: orb.live && orb.visible && Style.duration(100) > 0
    onTriggered: { orb.t += 0.04; orb.requestPaint() }
  }

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    var w = width, h = height
    var cx = w / 2, cy = h / 2
    var R = Math.min(w, h) / 2 * 0.98
    var c = orb.color
    var t = orb.t, e = orb.energy
    var breathe = orb.live ? 1 + 0.05 * Math.sin(t * 1.3) : 1
    function rgba(a) { return Qt.rgba(c.r, c.g, c.b, a) }

    for (var layer = 3; layer >= 0; layer--) {
      var rBase = R * (0.42 + layer * 0.13) * breathe + e * R * 0.08
      ctx.beginPath()
      for (var i = 0; i <= 64; i++) {
        var a = i / 64 * Math.PI * 2
        var wob = orb.live
          ? Math.sin(a * 3 + t * 1.7 + layer) * 0.5 + Math.sin(a * 5 - t * 2.3 + layer * 2) * 0.35 + Math.sin(a * 2 + t * 0.8) * 0.4
          : 0
        var r = Math.min(R, rBase + wob * (0.02 + e * 0.1) * R * (1 + layer * 0.3))
        var x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
      }
      ctx.closePath()
      var g = ctx.createRadialGradient(cx, cy - R * 0.15, R * 0.05, cx, cy, rBase * 1.2)
      g.addColorStop(0, rgba(0.95 - layer * 0.18))
      g.addColorStop(1, rgba(0.06))
      ctx.fillStyle = g
      ctx.fill()
    }
  }
}
