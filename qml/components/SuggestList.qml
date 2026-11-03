// Suggestions below an input field (instead of a pop-up window): sits above the layout, click selects.
// sets=true: set suggestions with bundle rows (highlighted) and indented single sets with type and year.
import QtQuick

Rectangle {
    id: s
    property var items: []
    property bool sets: false
    signal picked(var item)
    height: items.length ? Math.min(lv.contentHeight + 8, 340) : 0
    visible: height > 0
    radius: 10
    color: T.surface2
    border.width: 1; border.color: T.line2
    clip: true
    ListView {
        ScrollHint {}
        id: lv
        anchors.fill: parent; anchors.margins: 4
        model: s.items
        boundsBehavior: Flickable.StopAtBounds
        delegate: Rectangle {
            required property var modelData
            width: lv.width; height: 28
            radius: 6
            color: h.hovered ? T.button : "transparent"
            Row {
                x: 8 + (s.sets && modelData.child ? 16 : 0)
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                Text {
                    text: (modelData.done ? "✓ " : "") + (s.sets ? modelData.label : modelData.name)
                    color: s.sets && modelData.family ? T.text : (modelData.done ? T.dim : T.text2)
                    font.family: T.font; font.pixelSize: 13; font.bold: s.sets && modelData.family
                }
                Text {
                    text: s.sets ? (modelData.info || "") : (modelData.count || "")
                    color: T.dim; font.family: T.font; font.pixelSize: 11
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            HoverHandler { id: h; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: s.picked(modelData) }
        }
    }
}
