// The dock's "Sound" key opened (0.9.9, lead 14.11.2026): no pop-out – the dock itself grows upwards above the key
// (same glass, joined to the dock without a gap, like the tiles hint). A vertical slider for every scan sound:
// 10 steps, "off" at the bottom; drag, click or mouse wheel. The level is kept (scan_volume); whoever switches off
// stays off. Each change plays one tick at the new level (scansound.sample).
import QtQuick

Rectangle {
    id: col
    property int level: 0                 // 0 = off … levels
    property int levels: 10
    property string offText: "off"
    signal pick(int level)
    width: 62
    height: 214
    radius: T.tile.radius
    color: Qt.rgba(0.06, 0.06, 0.065, T.tile.glassStream)
    border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.09)
    // the lower corners are square and run into the dock: seamless with it
    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                anchors.leftMargin: 1; anchors.rightMargin: 1; height: col.radius + 1; color: col.color }
    Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 1; height: col.radius + 1
                color: col.border.color }
    Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 1; height: col.radius + 1
                color: col.border.color }

    Text {   // the level on top – "off" when 0
        id: num
        anchors.horizontalCenter: parent.horizontalCenter; y: 12
        text: col.level > 0 ? col.level : "–"
        color: col.level > 0 ? T.top : T.text2; font.family: T.font; font.pixelSize: 14; font.bold: true
    }
    Item {
        id: track
        anchors.horizontalCenter: parent.horizontalCenter
        y: num.y + num.height + 12
        width: 30; height: col.height - y - offLabel.height - 22
        readonly property real step: height / col.levels
        Rectangle {   // the groove
            anchors.horizontalCenter: parent.horizontalCenter; width: 4; height: parent.height; radius: 2
            color: Qt.rgba(1, 1, 1, 0.14)
        }
        Rectangle {   // filled from the bottom up to the knob
            anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom
            width: 4; radius: 2; height: track.height * col.level / col.levels
            color: col.level > 0 ? "#ededed" : "transparent"
        }
        Repeater {   // the steps as small marks beside the groove
            model: col.levels + 1
            Rectangle { required property int index
                        x: track.width / 2 + 6; y: track.height - index * track.step - 0.5
                        width: 3; height: 1; color: Qt.rgba(1, 1, 1, index <= col.level && col.level > 0 ? 0.5 : 0.2) }
        }
        Rectangle {   // the knob
            width: 16; height: 16; radius: 8
            anchors.horizontalCenter: parent.horizontalCenter
            y: track.height - track.height * col.level / col.levels - height / 2
            color: col.level > 0 ? "#ffffff" : T.off
            border.width: 1; border.color: Qt.rgba(0, 0, 0, 0.35)
        }
        MouseArea {
            anchors.fill: parent; anchors.margins: -10
            cursorShape: Qt.PointingHandCursor
            function at(my) {
                var v = Math.round((track.height - (my - 10)) / track.step)
                return Math.max(0, Math.min(col.levels, v))
            }
            onPressed: function (m) { var v = at(m.y); if (v !== col.level) col.pick(v) }
            onPositionChanged: function (m) { if (pressed) { var v = at(m.y); if (v !== col.level) col.pick(v) } }
            onWheel: function (w) {
                var v = Math.max(0, Math.min(col.levels, col.level + (w.angleDelta.y > 0 ? 1 : -1)))
                if (v !== col.level) col.pick(v)
                w.accepted = true
            }
        }
    }
    Text {   // "off" at the bottom – a click switches off
        id: offLabel
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: 12
        text: col.offText
        color: col.level === 0 ? T.top : (offMa.containsMouse ? T.text : T.text2)
        font.family: T.font; font.pixelSize: 12; font.bold: col.level === 0
        MouseArea { id: offMa; anchors.fill: parent; anchors.margins: -6; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor; onClicked: if (col.level !== 0) col.pick(0) }
    }
}
