// expand arrow (›), drawn like the other icons; open = rotated downwards (softly animated).
import QtQuick

Item {
    id: c
    property bool open: false
    property color color: T.text2
    property real size: 14
    width: size; height: size
    Canvas {
        id: cv
        onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
        anchors.fill: parent
        rotation: c.open ? 90 : 0
        Behavior on rotation { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        onPaint: {
            var g = getContext("2d"); g.reset()
            var s = width
            g.strokeStyle = c.color; g.lineWidth = Math.max(1.6, s * 0.14); g.lineCap = "round"; g.lineJoin = "round"
            g.beginPath(); g.moveTo(s * 0.36, s * 0.2); g.lineTo(s * 0.68, s * 0.5); g.lineTo(s * 0.36, s * 0.8); g.stroke()
        }
        Connections { target: c; function onColorChanged() { cv.requestPaint() } }
    }
}
