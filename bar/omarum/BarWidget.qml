import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarum.panel"

  property string state: "off"
  readonly property bool open: ["idle", "closed", "off"].indexOf(state) < 0
  readonly property var labels: ({
    "off": "not running", "idle": "ready", "closed": "ready", "listening": "listening",
    "user_speaking": "hearing you", "thinking": "thinking", "speaking": "talking", "error": "error"
  })

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰪥"
    active: root.open
    tooltipText: "Rum: " + (root.labels[root.state] || root.state) + "\nLeft-click: hands-free on/off · Right-click: settings"
    onPressed: function(button) {
      if (!root.bar) return
      if (button === Qt.RightButton) root.bar.run("omarum settings")
      else root.bar.run("omarum tap")
    }
  }

  Process {
    id: watcher
    command: ["omarum", "watch"]
    running: true
    stdout: SplitParser {
      onRead: data => { try { root.state = JSON.parse(data).state || "off" } catch (e) {} }
    }
    onExited: { root.state = "off"; restart.restart() }
  }

  Timer { id: restart; interval: 3000; onTriggered: watcher.running = true }
}
