import QtQuick
import qs.Commons

// "Halo": Rum's icon. A ring with a small bead on it (Rum sitting on her orb).
//   closed / idle: still · listening: the ring breathes · thinking: the bead circles
//   talking (you or Rum): the ring ripples with the voice.
// Drawn in one color (the bar's own foreground, like the other bar icons).
// Static when `live` is false, so a closed Rum costs nothing.
Canvas {
  id: icon

  property color color: Color.foreground
  property bool live: false       // animating at all
  property string rumState: "closed" // Rum's state from the engine
  property real energy: 0         // 0..1, how strongly a voice moves it
  property real t: 0

  implicitWidth: 16
  implicitHeight: 16
  antialiasing: true
  renderStrategy: Canvas.Cooperative

  onColorChanged: requestPaint()
  onLiveChanged: requestPaint()
  onRumStateChanged: requestPaint()
  onWidthChanged: requestPaint()

  Timer {
    // Frames only while alive; with animations off (Style.duration → 0) it stays still.
    interval: 33
    repeat: true
    running: icon.live && icon.visible && Style.duration(100) > 0
    onTriggered: { icon.t += 0.033; icon.requestPaint() }
  }

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    var s = Math.min(width, height), c = s / 2, t = icon.t
    var st = icon.live ? icon.rumState : "closed"
    var talking = st === "speaking" || st === "user_speaking"
    var lw = Math.max(1.3, s / 11)
    var R = s * 0.34 * (st === "listening" || st === "starting" ? 1 + 0.045 * Math.sin(t * 2.2) : 1)
    var amp = talking ? Math.max(0.15, icon.energy) * s * 0.065 : 0
    var col = icon.color
    ctx.lineWidth = lw
    ctx.strokeStyle = Qt.rgba(col.r, col.g, col.b, st === "error" ? 0.5 : 1)
    ctx.beginPath()
    for (var i = 0; i <= 96; i++) {
      var a = i / 96 * Math.PI * 2
      var r = R + amp * Math.sin(a * 6 + t * 9)
      var x = c + Math.cos(a) * r, y = c + Math.sin(a) * r
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.stroke()

    // The bead: upper right when still, circling while she thinks. A small gap is cut in the
    // ring around it so it reads as a separate thing at bar size.
    var ba = st === "thinking" ? t * 3.4 - Math.PI / 2 : -Math.PI / 4
    var bx = c + Math.cos(ba) * R, by = c + Math.sin(ba) * R, br = s * 0.12
    ctx.save()
    ctx.globalCompositeOperation = "destination-out"
    ctx.beginPath(); ctx.arc(bx, by, br + lw * 0.9, 0, 2 * Math.PI); ctx.fill()
    ctx.restore()
    ctx.fillStyle = Qt.rgba(col.r, col.g, col.b, 1)
    ctx.beginPath(); ctx.arc(bx, by, br, 0, 2 * Math.PI); ctx.fill()
  }
}
