// Small card back (pixel art, userprofile.py) at height h – sharp pixels, rounded corners.
// Understands all formats: old (280 hex characters = 14 × 20), v2 ("v2;28x40;c1;…", 32 fixed colours from palette) and
// v3 ("v3;28x40;c1;<Farben>;…", own colours – palette is not needed then).
import QtQuick

Item {
    id: root
    property string back: ""
    property var palette: []          // only for v1/v2: the 32 fixed colours (userprofile.PALETTE)
    property real h: 60
    readonly property string digits: "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    readonly property var d: {
        var b = root.back || ""
        if (b.indexOf("v3;") === 0) {
            var q = b.split(";"), wh3 = (q[1] || "").split("x")
            return {w: parseInt(wh3[0]) || 28, h: parseInt(wh3[1]) || 40, cells: q.slice(4).join(""),
                    colors: (q[3] || "").split(",").map(function (c) { return "#" + c })}
        }
        if (b.indexOf("v2;") === 0) {
            var p = b.split(";"), wh = (p[1] || "").split("x")
            return {w: parseInt(wh[0]) || 14, h: parseInt(wh[1]) || 20, cells: p.slice(3).join(";"), colors: root.palette}
        }
        return {w: 14, h: 20, cells: b, colors: root.palette}
    }
    readonly property real rad: Math.max(2, width * 0.09)   // corners always rounded
    width: Math.round(h * 14 / 20); height: h
    onBackChanged: cv.requestPaint()
    onPaletteChanged: cv.requestPaint()

    Canvas {
        onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
        id: cv
        anchors.fill: parent
        renderStrategy: Canvas.Cooperative
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onVisibleChanged: if (visible) requestPaint()   // templates otherwise sometimes stayed empty
        Component.onCompleted: Qt.callLater(requestPaint)
        onPaint: {
            var g = getContext("2d")
            g.reset()
            var d = root.d, cw = width / d.w, ch = height / d.h, r = root.rad
            g.save()
            g.beginPath()   // corners: cut out rounded
            g.moveTo(r, 0); g.lineTo(width - r, 0); g.arcTo(width, 0, width, r, r)
            g.lineTo(width, height - r); g.arcTo(width, height, width - r, height, r)
            g.lineTo(r, height); g.arcTo(0, height, 0, height - r, r)
            g.lineTo(0, r); g.arcTo(0, 0, r, 0, r); g.closePath()
            g.clip()
            if (d.cells.length === d.w * d.h && d.colors && d.colors.length) {
                for (var i = 0; i < d.cells.length; i++) {
                    g.fillStyle = d.colors[root.digits.indexOf(d.cells[i])] || "#000"
                    g.fillRect(Math.floor((i % d.w) * cw), Math.floor(Math.floor(i / d.w) * ch), Math.ceil(cw) + 1, Math.ceil(ch) + 1)
                }
            }
            g.restore()
        }
    }
    Rectangle { anchors.fill: parent; radius: root.rad; color: "transparent"; border.width: 1; border.color: T.line2 }
}
