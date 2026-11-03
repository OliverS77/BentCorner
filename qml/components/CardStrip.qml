// Horizontal strip of card images to browse (mouse wheel scrolls sideways). items: [{img, text, sub, tip,
// hi, head}] – hi = highlighted (matches the camera image), head = small heading above the tile (a new set starts).
// current = the marked tile (Enter takes it), scrolled into view. Click reports picked(index).
import QtQuick

ListView {
    ScrollHint {}
    id: root
    property real tileH: 230
    property int current: -1
    readonly property real headH: 18
    signal picked(int index)
    onCurrentChanged: if (current >= 0) positionViewAtIndex(current, ListView.Contain)
    Component.onCompleted: if (current >= 0) positionViewAtIndex(current, ListView.Contain)
    orientation: ListView.Horizontal
    spacing: 10
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    implicitHeight: tileH + 52 + headH
    WheelHandler {
        onWheel: function (ev) {
            var d = ev.angleDelta.y || ev.angleDelta.x
            root.contentX = Math.max(0, Math.min(root.contentWidth - root.width, root.contentX - d))
        }
    }
    delegate: Rectangle {
        id: tile
        required property var modelData
        required property int index
        width: root.tileH * 63 / 88 + 16; height: root.tileH + 50 + root.headH
        radius: 10
        color: "transparent"
        Text { width: parent.width; height: root.headH; elide: Text.ElideRight; text: tile.modelData.head || ""
               color: T.muted; font.family: T.font; font.pixelSize: 11; font.bold: true }
        Rectangle {
            y: root.headH; width: parent.width; height: parent.height - root.headH; radius: 10
            color: Qt.darker(T.surface, 1.1)
            border.width: th.hovered || tile.index === root.current ? 2 : 1
            border.color: th.hovered || tile.index === root.current ? T.text : (tile.modelData.hi ? T.text2 : T.line)
        }
        Image {
            id: stripImg
            x: 8; y: 8 + root.headH; width: parent.width - 16; height: root.tileH
            source: tile.modelData.img || ""
            asynchronous: true; fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true
            sourceSize.height: root.tileH * 2
        }
        NoImage {   // no image: crossed-out card in card proportions (the name stands below)
            thumb: true
            height: stripImg.height; width: height * 63 / 88; anchors.centerIn: stripImg
            visible: (tile.modelData.img || "") === "" || stripImg.status === Image.Error
        }
        Column {
            x: 8; y: root.tileH + 12 + root.headH; width: parent.width - 16
            Text { width: parent.width; elide: Text.ElideRight; text: tile.modelData.text || ""
                   color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true; horizontalAlignment: Text.AlignHCenter }
            Text { width: parent.width; elide: Text.ElideRight; text: tile.modelData.sub || ""
                   color: T.muted; font.family: T.font; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter }
        }
        HoverHandler { id: th; cursorShape: Qt.PointingHandCursor
                       onHoveredChanged: if (hovered && tile.modelData.tip) tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) } }
        Timer { id: tipT; interval: 650
                onTriggered: { var p = tile.mapToItem(null, tile.width / 2, tile.height); shell.tip(tile.modelData.tip, p.x, p.y) } }
        TapHandler { onTapped: root.picked(tile.index) }
    }
}
