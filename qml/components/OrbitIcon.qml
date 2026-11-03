// Bent°Corner Orbit, drawn for any level between 0 and 2 (the slider glides through it):
// Core = filled circle · Near Orbit = plus a track open at the top right with the planet (a filled dot – the ° of
// Bent°Corner) in the gap · Full Orbit = plus a second, outer track with its planet. While the level grows a track
// draws itself in and its planet runs a little way along. Stroke at least 1.5 px even when small.
import QtQuick

Canvas {
    id: c
    property real lv: 0              // 0 Core … 1 Near Orbit … 2 Full Orbit (in between while sliding)
    property color color: T.text
    property color faint: T.line2    // the tracks still to come, as a hint
    implicitWidth: 120; implicitHeight: 120
    renderStrategy: Canvas.Cooperative
    onLvChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onAvailableChanged: if (available) requestPaint()

    onPaint: {
        var g = getContext("2d")
        g.reset()
        var R = Math.min(width, height) / 2
        g.translate(width / 2, height / 2)
        var lw = Math.max(1.5, R * 0.07)
        g.lineWidth = lw
        g.lineCap = "round"
        function clamp(v) { return Math.max(0, Math.min(1, v)) }
        function track(r, p, home) {
            var gap = Math.max(0.28, 2.1 * lw / r)   // the gap around the planet
            // hint of the whole track (dotted feel: faint), then the drawn part
            g.strokeStyle = c.faint
            g.globalAlpha = 0.5 * (1 - p)
            g.beginPath(); g.arc(0, 0, r, home + gap, home - gap + Math.PI * 2, false); g.stroke()
            if (p <= 0) return
            var pa = home - 0.9 * (1 - p)          // the planet runs along to its place
            g.globalAlpha = 1
            g.strokeStyle = c.color
            g.beginPath(); g.arc(0, 0, r, pa + gap, pa + gap + (Math.PI * 2 - 2 * gap) * p, false); g.stroke()
            g.fillStyle = c.color
            g.beginPath(); g.arc(r * Math.cos(pa), r * Math.sin(pa), lw * 1.35 + R * 0.025, 0, Math.PI * 2); g.fill()
        }
        g.fillStyle = c.color
        g.beginPath(); g.arc(0, 0, R * 0.2, 0, Math.PI * 2); g.fill()          // the core: your collection
        track(R * 0.52, clamp(lv), -Math.PI / 4)                                 // near: top right
        track(R * 0.86, clamp(lv - 1), -Math.PI / 4 - 0.42)                      // full: a little further round
    }
}
