// Advanced search entry (like libview.TriCheck): box with checkmark (must/on) or red ✕ (exclude/off);
// click cycles on, double click = only this one (again: all except this one). On change the mark pops briefly.
import QtQuick

Item {
    id: tr
    property string text
    property int state: 0
    property bool binary: false
    signal clicked()
    signal solo()
    implicitWidth: 22 + label.implicitWidth + 8
    height: 24

    property real pop: 1
    onStateChanged: popAnim.restart()
    NumberAnimation { id: popAnim; target: tr; property: "pop"; from: 0; to: 1; duration: 260; easing.type: Easing.OutBack }

    Rectangle {
        anchors.fill: parent
        radius: 6
        color: h.hovered ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
    }
    Rectangle {
        id: box
        x: 3; anchors.verticalCenter: parent.verticalCenter
        width: 16; height: 16; radius: 4
        color: "transparent"
        border.width: 1.3
        border.color: tr.state === 2 ? "#d0606c" : (tr.state === 1 ? T.accent : T.line2)
        Canvas {
            onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
            anchors.fill: parent
            scale: 0.6 + 0.4 * tr.pop
            property int st: tr.state
            onStChanged: requestPaint()
            onPaint: {
                var g = getContext("2d"); g.reset(); g.lineWidth = 2; g.lineCap = "round"; g.lineJoin = "round"
                if (st === 1) { g.strokeStyle = T.accent; g.beginPath(); g.moveTo(3.5, 8.5); g.lineTo(6.6, 11.6); g.lineTo(12.5, 4.6); g.stroke() }
                else if (st === 2) { g.strokeStyle = "#ff5d6c"; g.beginPath(); g.moveTo(4.5, 4.5); g.lineTo(11.5, 11.5); g.moveTo(11.5, 4.5); g.lineTo(4.5, 11.5); g.stroke() }
            }
        }
    }
    Text {
        id: label
        x: 24
        width: tr.width - 26
        anchors.verticalCenter: parent.verticalCenter
        text: tr.text
        elide: Text.ElideRight
        color: tr.state === 2 ? "#ff9aa3" : T.text
        font.family: T.font; font.pixelSize: 13
        font.strikeout: tr.state === 2 && !tr.binary
    }
    HoverHandler { id: h; cursorShape: Qt.PointingHandCursor }
    TapHandler {
        id: tap
        // every click goes to Python – a double click is detected there by timing (after the first click
        // this checkbox is rebuilt, a local double-click counter would start at 1 again)
        onTapped: tr.clicked()
    }
}
