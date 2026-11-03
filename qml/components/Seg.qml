// Toggle made of small keys (OR/AND, contains/exactly/at most, source, price type …) – the same key as all
// buttons (Key.qml): selected = little lamp lights up and the text is bright, the key stays up.
import QtQuick

Row {
    id: s
    property var items: []        // [{key, text, tip?}]
    property string current: ""
    property var multi: null      // multi-select: list of the switched-on keys (instead of current)
    signal picked(string key)
    spacing: 8
    opacity: enabled ? 1 : 0.45
    Repeater {
        model: s.items
        Item {
            id: sg
            required property var modelData
            readonly property bool on: s.multi ? s.multi.indexOf(modelData.key) >= 0 : modelData.key === s.current
            readonly property bool off: modelData.disabled === true   // does not exist (e.g. print only as foil)
            opacity: off ? 0.35 : 1
            property real hv: h.hovered ? 1 : 0
            Behavior on hv { NumberAnimation { duration: 150 } }
            height: 28
            width: t.implicitWidth + 36
            Key { anchors.fill: parent; radius: 8; down: tap.pressed }
            Rectangle {   // little lamp: off = grey, on = lit
                x: 11; anchors.verticalCenter: parent.verticalCenter
                width: 5; height: 5; radius: 2.5
                color: sg.on ? T.hi : T.off   // flat: off grey, on white
                Behavior on color { ColorAnimation { duration: 200 } }
            }
            Text {
                id: t
                x: 23; anchors.verticalCenter: parent.verticalCenter
                text: modelData.text
                color: Qt.tint(sg.on ? "#ececec" : "#a6a6a6", Qt.rgba(0.957, 0.957, 0.957, sg.hv))
                font.family: T.font; font.pixelSize: 12; font.bold: true
            }
            HoverHandler { id: h; cursorShape: Qt.PointingHandCursor
                onHoveredChanged: if (hovered && sg.modelData.tip) { var p = sg.mapToItem(null, sg.width / 2, sg.height); shell.tip(sg.modelData.tip, p.x, p.y) } else shell.tip("", 0, 0) }
            TapHandler { id: tap; gesturePolicy: TapHandler.ReleaseWithinBounds; enabled: s.enabled && !sg.off; onTapped: s.picked(sg.modelData.key) }
        }
    }
}
