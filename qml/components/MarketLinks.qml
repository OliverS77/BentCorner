// „More marketplaces“ at the prices: one row with an arrow that expands – without its own box (it already
// sits in one), only fine lines.
// Inside: eBay – below, set apart, „Local“ (classifieds). Cardmarket and TCGplayer already sit directly at their
// prices. A click opens the card's page in the browser; nothing is queried automatically.
import QtQuick

Rectangle {
    id: ml
    property var links: []          // [{key, label, host, url, group: "main" | "local"}]
    property bool open: false
    visible: links.length > 0
    width: parent ? Math.min(parent.width, 340) : 340
    height: headRow.height + (open ? inner.implicitHeight + 8 : 0)
    Behavior on height { enabled: shell.animate; NumberAnimation { duration: 200 * shell.speed; easing.type: Easing.OutCubic } }
    clip: true
    color: "transparent"
    Rectangle { width: parent.width; height: 1; color: T.line }   // fine line on top instead of a border
    readonly property var mainLinks: links.filter(function (m) { return m.group !== "local" })
    readonly property var localLinks: links.filter(function (m) { return m.group === "local" })

    component Entry: Rectangle {
        id: en
        property var m
        width: inner.width; height: 30; radius: 7
        color: eh.hovered ? T.surface2 : "transparent"
        Text { x: 10; anchors.verticalCenter: parent.verticalCenter; text: en.m.label
               color: eh.hovered ? T.text : T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
        Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
               text: en.m.host + "  ↗"; color: eh.hovered ? T.muted : T.dim; font.family: T.font; font.pixelSize: 11 }
        HoverHandler { id: eh; cursorShape: Qt.PointingHandCursor }
        TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: Qt.openUrlExternally(en.m.url) }
    }

    Item {   // header row = toggle
        id: headRow
        width: parent.width; height: 34
        Text { x: 0; anchors.verticalCenter: parent.verticalCenter
               text: shell.text("Other marketplaces")
               color: hh.hovered || ml.open ? T.text : T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
        Text { anchors.right: parent.right; anchors.rightMargin: 2; anchors.verticalCenter: parent.verticalCenter
               text: ml.open ? "▴" : "▾"; color: hh.hovered ? T.text : T.muted; font.pixelSize: 12 }
        HoverHandler { id: hh; cursorShape: Qt.PointingHandCursor
            onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height)
                shell.tip(shell.text("View the card on eBay & co. – opens the page in your browser"), p.x, p.y) } else shell.tip("", 0, 0) }
        TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: ml.open = !ml.open }
    }
    Column {
        id: inner
        x: 0; y: headRow.height; width: parent.width
        spacing: 2
        opacity: ml.open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 160 } }
        Repeater { model: ml.mainLinks; Entry { required property var modelData; m: modelData } }
        Item {   // set apart: local classifieds
            visible: ml.localLinks.length > 0
            width: inner.width; height: 24
            Rectangle { y: 5; x: 4; width: parent.width - 8; height: 1; color: T.line }
            Text { x: 10; y: 10; text: shell.text("LOCAL"); color: T.dim
                   font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.1 }
        }
        Repeater { model: ml.localLinks; Entry { required property var modelData; m: modelData } }
    }
}
