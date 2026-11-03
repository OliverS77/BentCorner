// Small chip on a list („automatic“, „private“ / „shared“). lit = bright (e.g. shared). Click -> clicked.
import QtQuick

Rectangle {
    id: c
    property string text: ""
    property string tip: ""
    property bool lit: false
    signal clicked()
    width: ct.implicitWidth + 14; height: 20; radius: 10
    color: ch.hovered ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
    border.width: 1; border.color: c.lit ? "#dedede" : T.line2
    Text { id: ct; anchors.centerIn: parent; text: c.text; color: c.lit ? "#ececec" : T.muted
           font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 0.4 }
    HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor
        onHoveredChanged: if (hovered && c.tip) { var p = c.mapToItem(null, c.width / 2, c.height + 2); shell.tip(c.tip, p.x, p.y) }
                          else shell.tip("", 0, 0) }
    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: { shell.tip("", 0, 0); c.clicked() } }
}
