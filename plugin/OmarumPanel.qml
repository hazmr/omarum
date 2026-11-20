import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

// Omarum in the bar: Rum's orb, and a panel with hands-free, the engine, the
// last conversation and settings. Left-click opens the panel, right-click
// toggles hands-free, middle-click opens settings.
Panel {
  id: root
  moduleName: "omarum.panel"
  ipcTarget: "omarum.panel"
  manageIpc: false

  readonly property string state: engine.state
  readonly property string reason: engine.phase === "running" ? engine.reason : (engine.reason || engine.setupMessage)
  readonly property var info: engine.info
  property int cursor: 0          // -1 = the hands-free switch, 0.. = rows
  property bool cursorActive: false
  property real energy: 0
  property real clock: 0

  readonly property bool running: state !== "off"
  readonly property bool settingUp: engine.phase === "checking" || engine.phase === "setup" || engine.phase === "starting"
  readonly property bool open_: ["idle", "closed", "off", "error"].indexOf(state) < 0
  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property var colors: info.colors || ({ user: "#cc8979", companion: "#82c9ed", idle: "#584e51", error: "#ee7350" })
  readonly property string name: info.name || "Rum"
  readonly property var labels: ({
    off: "starting", starting: "waking up", idle: "ready", closed: "ready", listening: "listening",
    user_speaking: "hearing you", thinking: "thinking", speaking: "talking", error: "something went wrong"
  })

  // The orb's colors (theme.state_color): you, Rum, or resting.
  function orbColor(onBar) {
    if (state === "user_speaking") return colors.user
    if (state === "speaking") return colors.companion
    if (state === "thinking") return colors.thinking || colors.idle
    if (state === "listening" || state === "starting") return colors.idle
    if (state === "error") return colors.error
    return onBar ? Qt.darker(root.barForeground, running ? 1.0 : 1.55) : colors.companion
  }

  readonly property var rows: {
    var out = []
    if (engine.phase === "needs-uv") out.push({ icon: "󰏗", label: "Install uv", value: "", cmd: "install-uv" })
    if (engine.phase === "failed") out.push({ icon: "󰑓", label: "Try again", value: "", cmd: "retry" })
    out.push({ icon: "󰧑", label: "Brain", value: info.brain || "", tab: "engine" })
    out.push({ icon: "󰍬", label: "Ears", value: info.ears || "", tab: "engine" })
    out.push({ icon: "󰕾", label: "Voice", value: info.voice || "", tab: "engine" })
    out.push({ icon: "󰌌", label: "Talk", value: info.shortcut || "", tab: "companion" })
    if (info.last) out.push({ last: true, label: info.last.text || "…", value: [info.last.when, info.last.length].filter(function(s) { return s }).join(" · "), tab: "conversations" })
    out.push({ icon: "󰆼", label: "Conversations", value: info.talks !== undefined ? String(info.talks) : "", tab: "conversations", chevron: true })
    out.push({ icon: "󰒓", label: "Settings", value: "", tab: "companion", chevron: true })
    return out
  }

  function tap() { if (running) engine.send("tap") }
  function openSettings(tab) { engine.openSettings(tab); root.close() }
  function activate() {
    if (cursor < 0) { tap(); return }
    var r = rows[cursor]
    if (!r) return
    if (r.tab) openSettings(r.tab)
    else if (r.cmd === "install-uv") Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", "omarchy pkg add uv"])
    else if (r.cmd === "retry") engine.retry()
  }
  function move(dy) {
    cursorActive = true
    var top = running ? -1 : 0
    cursor = Math.max(top, Math.min(rows.length - 1, cursor + dy))
  }
  function refresh() { engine.refreshInfo() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    cursorActive = false
    cursor = running ? -1 : 0
    refresh()
    Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.forceActiveFocus() })
  }
  Engine { id: engine }
  Orb { engine: engine }
  TalkShortcut { engine: engine }

  ShellIpc {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.refresh(); return "ok" }
    function status(): string { return root.state }
    function tap(): void { root.tap() }
    function talkDown(): void { engine.send("ptt_down") }
    function talkUp(): void { engine.send("ptt_up") }
  }

  // A voice-like pulse while someone talks (the bar has no audio levels).
  Timer {
    interval: 50
    repeat: true
    running: root.state === "speaking" || root.state === "user_speaking"
    onTriggered: {
      root.clock += 0.05
      var t = root.clock, seed = root.state === "speaking" ? 1.7 : 0.3
      var syl = Math.max(0, Math.sin(t * 7.3 + seed)) * Math.max(0, Math.sin(t * 2.1 + seed * 2))
      root.energy = Math.min(1, 0.25 + syl * 0.9)
    }
    onRunningChanged: if (!running) root.energy = 0
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: root.name + ": " + (root.labels[root.state] || root.state) + (root.state === "error" && root.reason ? "\n" + root.reason : "")
    iconComponent: Component {
      Item {
        OrbIcon {
          anchors.centerIn: parent
          width: button.iconSize * 1.15
          height: width
          color: root.orbColor(true)
          live: root.open_
          energy: root.energy
        }
      }
    }
    onPressed: function(code) {
      if (code === Qt.RightButton) root.tap()
      else if (code === Qt.MiddleButton) root.openSettings("")
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(560))

    content: PanelKeyCatcher {
      implicitHeight: column.implicitHeight
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        root.move(dy)
      }
      onActivateRequested: if (root.cursorActive) root.activate()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === " " || t === "h" || t === "H") root.tap()
        else if (t === "s" || t === "S") root.openSettings("")
      }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(10)

        Item {
          id: header
          width: parent.width
          implicitHeight: hero.implicitHeight
          readonly property bool ringVisible: root.cursorActive && root.cursor === -1

          PanelHero {
            id: hero
            width: parent.width
            title: root.name
            meta: root.settingUp ? (engine.phase === "setup" ? "setting up" : "starting") : (engine.phase === "needs-uv" || engine.phase === "failed" ? "needs attention" : (root.labels[root.state] || root.state))
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconComponent: Component {
              OrbIcon {
                width: Style.font.display * 1.25
                height: width
                color: root.orbColor(false)
                live: root.running
                energy: root.energy
                opacity: root.running ? 1 : 0.45
              }
            }
            trailingControl: Component {
              ToggleSwitch {
                id: handsFree
                visible: root.running
                checked: root.open_
                hasCursor: header.ringVisible
                foreground: hero.foreground
                onHovered: function(on) { if (on) { root.cursorActive = true; root.cursor = -1 } }
                onToggled: root.tap()

                PanelToolTip {
                  visible: handsFree.containsMouse
                  text: root.open_ ? "Close the conversation" : "Talk hands-free"
                  fontFamily: hero.fontFamily
                }
              }
            }
          }
        }

        Text {
          visible: root.reason !== "" && (root.state === "error" || engine.phase !== "running")
          width: parent.width
          textFormat: Text.PlainText
          text: root.reason
          color: root.settingUp ? root.dim : (bar ? bar.urgent : Commons.Color.urgent)
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        PanelSeparator { foreground: root.foreground }

        Column {
          width: parent.width
          spacing: Style.space(2)

          Repeater {
            model: root.rows
            delegate: Column {
              required property var modelData
              required property int index
              width: parent.width
              spacing: Style.space(2)

              PanelSeparator {
                visible: modelData.last === true || (modelData.chevron === true && !(index > 0 && root.rows[index - 1].chevron))
                foreground: root.foreground
              }
              PanelSectionHeader {
                visible: modelData.last === true
                text: "Last conversation"
                foreground: root.foreground
                fontFamily: root.fontFamily
              }
              Row_ { width: parent.width; row: modelData; rowIndex: index }
            }
          }
        }
      }
    }
  }

  component Row_: CursorSurface {
    id: line
    property var row: ({})
    property int rowIndex: 0

    hasCursor: root.cursorActive && root.cursor === rowIndex
    foreground: root.foreground
    implicitHeight: content.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: { root.cursorActive = true; root.cursor = line.rowIndex }
      onClicked: { root.cursor = line.rowIndex; root.activate() }
    }

    RowLayout {
      id: content
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(10)

      Text {
        visible: !line.row.last
        textFormat: Text.PlainText
        text: line.row.icon || ""
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.icon
        Layout.alignment: Qt.AlignVCenter
      }

      // An ordinary row: label on the left, value on the right.
      Text {
        visible: !line.row.last
        textFormat: Text.PlainText
        text: line.row.label || ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        Layout.alignment: Qt.AlignVCenter
      }
      Text {
        visible: !line.row.last
        textFormat: Text.PlainText
        text: (line.row.value || "") + (line.row.chevron || line.row.value ? "  ›" : "")
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        elide: Text.ElideLeft
        horizontalAlignment: Text.AlignRight
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
      }

      // The last conversation: what you said first, then when and how long.
      ColumnLayout {
        visible: line.row.last === true
        Layout.fillWidth: true
        spacing: Style.space(2)
        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          text: line.row.label || ""
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.WordWrap
          maximumLineCount: 2
          elide: Text.ElideRight
        }
        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          text: line.row.value || ""
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
