// Card image MISSING (the source has none, or it failed) – the user's design (2026-10-26): solid card outline and a solid
// diagonal from bottom left to top right, in the text colour. Small (thumbnails): nothing else – name and number stand
// under the tile where it has them. Large (from bigFrom px wide, not a thumbnail): "Image not available" in the middle,
// the line leaves a gap around the text. thumb: true for every tile/strip/list – never text, whatever its size.
// Deliberately different from "still loading" (Shimmer: light stripe with the name). Greyscale from T only, so it works
// in the dark and the light look.
// Every card tile carries one, almost always hidden: the drawing (Shape + Text) is only built while it shows – hidden it
// is one empty item, not ten (each item in the window costs in every frame, see ViewPane).
import QtQuick
import QtQuick.Shapes

Item {
    id: n
    property real radius: Math.max(4, width * 0.045)
    property real bigFrom: 180                       // from this width: the text in the middle
    property bool thumb: false                       // tile, strip, list row: never text (the user's rule)
    readonly property bool big: !thumb && width >= bigFrom

    Loader {
        anchors.fill: parent
        active: n.visible && n.width > 0
        sourceComponent: Item {
            id: d
            readonly property color ink: T.text
            readonly property color line: Qt.rgba(ink.r, ink.g, ink.b, 0.55)
            readonly property real lw: Math.max(1.2, width / 90)
            // the diagonal: bottom left -> top right, stopping short of the rounded corners
            readonly property real inset: n.radius * 0.9
            readonly property real ax: inset
            readonly property real ay: height - inset
            readonly property real bx: width - inset
            readonly property real by: inset
            // gap around the text: the part of the line inside the text box (+ margin) is left out (the line runs
            // through the middle, so the gap is symmetric around t = 0.5)
            readonly property real gapW: n.big ? msg.paintedWidth / 2 + 10 : 0
            readonly property real gapH: n.big ? msg.paintedHeight / 2 + 8 : 0
            readonly property real dt: n.big ? Math.min(gapW / Math.max(1, bx - ax), gapH / Math.max(1, ay - by)) : 0

            Rectangle { anchors.fill: parent; radius: n.radius; color: Qt.rgba(d.ink.r, d.ink.g, d.ink.b, 0.025) }
            Shape {
                anchors.fill: parent; antialiasing: true; preferredRendererType: Shape.CurveRenderer
                ShapePath {   // outline
                    strokeColor: d.line; strokeWidth: d.lw; fillColor: "transparent"
                    PathRectangle { x: d.lw / 2; y: d.lw / 2; width: d.width - d.lw; height: d.height - d.lw; radius: n.radius }
                }
                ShapePath {   // diagonal, first part (up to the text – or all the way when small)
                    strokeColor: d.line; strokeWidth: d.lw; capStyle: ShapePath.RoundCap
                    startX: d.ax; startY: d.ay
                    PathLine { x: d.ax + (d.bx - d.ax) * (0.5 - d.dt) * (n.big ? 1 : 2)
                               y: d.ay + (d.by - d.ay) * (0.5 - d.dt) * (n.big ? 1 : 2) }
                }
                ShapePath {   // second part, after the text (only when big)
                    strokeColor: n.big ? d.line : "transparent"; strokeWidth: d.lw; capStyle: ShapePath.RoundCap
                    startX: d.ax + (d.bx - d.ax) * (0.5 + d.dt); startY: d.ay + (d.by - d.ay) * (0.5 + d.dt)
                    PathLine { x: d.bx; y: d.by }
                }
            }
            Text {
                id: msg
                visible: n.big
                anchors.centerIn: parent
                width: Math.min(implicitWidth, n.width * 0.7)
                text: shell.text("Image not available")
                wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
                color: T.text2; font.family: T.font; font.pixelSize: Math.max(12, Math.round(n.width / 17))
            }
        }
    }
}
