// Instead of the price chart while there is no history: short hint – while loading with time left („about 2 min left“),
// otherwise – if possible – „Load price history“. Once the history is there, the chart appears by itself.
import QtQuick

Rectangle {
    id: ph
    property var hint: ({})
    signal load()
    height: col.implicitHeight + 24
    radius: 12
    color: "transparent"
    border.width: 1; border.color: T.line
    property real now: Date.now()
    Timer { interval: 5000; repeat: true; running: ph.visible && (ph.hint.until || 0) > 0; onTriggered: ph.now = Date.now() }
    readonly property string rest: {
        var u = ph.hint.until || 0
        if (!u) return ""
        var min = Math.ceil((u - ph.now) / 60000)
        return min <= 1 ? shell.text("almost done") : shell.text("about") + " " + min + " " + shell.text("min left")
    }
    Column {
        id: col
        x: 14; y: 12; width: parent.width - 28
        spacing: 10
        Text { width: parent.width; wrapMode: Text.Wrap
               text: (ph.hint.text || "") + (ph.rest !== "" ? " – " + ph.rest : (ph.hint.loading === true ? " …" : ""))
               color: T.muted; font.family: T.font; font.pixelSize: 12 }
        Btn { visible: ph.hint.canLoad === true; height: 30; compact: true; width: implicitWidth + 12
              text: shell.text("Load price history"); onClicked: ph.load() }
    }
}
