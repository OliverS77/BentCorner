// Price history (like libview.PriceChart): Cardmarket and TCGplayer (converted) in the display currency; on top
// Normal/Foil and time range; hover shows the date and both prices.
import QtQuick

Item {
    id: ch
    property var info: ({})   // not „data“ – in Qt Quick that is already the list of children
    signal finishPicked(string k)
    signal rangePicked(int days)
    height: legend.y + legend.height + 10 + 230   // legend (possibly below the buttons) – the plot area moves down
    readonly property var lines: info && info.lines ? info.lines : []
    property real hx: -1

    // style: Cardmarket solid, TCGplayer dashed · normal light, foil gold · chosen finish bold
    readonly property color gold: "#d9b46a"
    function lineColor(l) { return l.foil ? ch.gold : T.text }
    property var hidden: ({})          // name -> hidden (click on the legend)
    property int hiddenRev: 0
    readonly property var shownLines: {
        var r = hiddenRev, out = []
        for (var i = 0; i < lines.length; i++) if (!hidden[lines[i].name]) out.push(lines[i])
        return out
    }
    // legend: one platform per row (normal, foil) – click hides/shows a line
    readonly property var legendLines: {
        var out = []
        for (var s = 0; s < 2; s++) for (var f = 0; f < 2; f++)
            for (var i = 0; i < lines.length; i++)
                if ((lines[i].shop === "t") === (s === 1) && (lines[i].foil === true) === (f === 1)) out.push(lines[i])
        return out
    }
    Grid {
        id: legend
        // fits next to the time range buttons? otherwise below
        y: implicitWidth + rangeRow.width + 16 > ch.width ? rangeRow.height + 8 : 0
        columns: 2
        columnSpacing: 16; rowSpacing: 6
        Repeater {
            model: ch.legendLines
            Row {
                required property var modelData
                readonly property bool off: ch.hiddenRev >= 0 && !!ch.hidden[modelData.name]
                spacing: 6
                opacity: off ? 0.35 : (modelData.dim ? 0.6 : 1)
                Canvas {
                    width: 16; height: 12; anchors.verticalCenter: parent.verticalCenter
                    property var l: parent.modelData
                    onLChanged: requestPaint()
                    onAvailableChanged: if (available) requestPaint()
                    onPaint: { var g = getContext("2d"); g.reset(); g.strokeStyle = ch.lineColor(l); g.lineWidth = 2
                        g.setLineDash(l.shop === "t" ? [3, 2] : []); g.beginPath(); g.moveTo(0, 6); g.lineTo(16, 6); g.stroke() }
                }
                Text { text: modelData.name; color: T.text2; font.family: T.font; font.pixelSize: 11 }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds
                             onTapped: { ch.hidden[modelData.name] = !ch.hidden[modelData.name]; ch.hiddenRev++ } }
            }
        }
    }
    Row {
        id: rangeRow
        anchors.right: parent.right
        spacing: 6
        Repeater {
            model: ch.info.ranges || []
            Btn { required property var modelData; compact: true; text: modelData.text
                  active: ch.info.days === modelData.days; onClicked: ch.rangePicked(modelData.days) }
        }
    }
    Canvas {
        onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
        id: cv
        y: legend.y + legend.height + 10
        width: parent.width; height: Math.max(1, parent.height - y)   // never 0/negative (else never ready to paint)
        property var lines: ch.shownLines
        onLinesChanged: requestPaint()
        onWidthChanged: requestPaint()
        property real hx: ch.hx
        onHxChanged: requestPaint()
        onPaint: {
            var g = getContext("2d"); g.reset()
            var L = lines
            var left = 64, top = 30, right = width - 10, bottom = height - 24
            if (!L || !L.length) {
                g.fillStyle = T.dim; g.font = "13px " + T.font; g.textAlign = "center"
                g.fillText(shell.text("No history for this finish"), width / 2, height / 2); return
            }
            var t0 = 1e18, t1 = 0, lo = 1e18, hi = 0
            for (var i = 0; i < L.length; i++) for (var j = 0; j < L[i].pts.length; j++) {
                var p = L[i].pts[j]; t0 = Math.min(t0, p[0]); t1 = Math.max(t1, p[0]); lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]) }
            var pad = Math.max((hi - lo) * 0.12, hi * 0.03, 0.05)
            lo = Math.max(0, lo - pad); hi = hi + pad
            var span = Math.max(1, t1 - t0)
            function X(t) { return left + (right - left) * (t - t0) / span }
            function Y(v) { return bottom - (bottom - top) * (v - lo) / (hi - lo) }
            g.font = "10px " + T.font
            for (var k = 0; k < 4; k++) {
                var v = lo + (hi - lo) * k / 3, yy = Y(v)
                g.strokeStyle = Qt.rgba(1, 1, 1, k ? 0.06 : 0.12); g.lineWidth = 1
                g.beginPath(); g.moveTo(left, yy); g.lineTo(right, yy); g.stroke()
                g.fillStyle = T.dim; g.textAlign = "right"
                g.fillText(v.toFixed(2).replace(".", ",") + " €", left - 6, yy + 3)
            }
            g.textAlign = "left"; g.fillStyle = T.dim
            g.fillText(new Date(t0).toLocaleDateString(Qt.locale(), "dd.MM.yy"), left, bottom + 16)
            g.textAlign = "right"
            g.fillText(new Date(t1).toLocaleDateString(Qt.locale(), "dd.MM.yy"), right, bottom + 16)
            var order = []   // dimmed ones first, the chosen finish on top
            for (var a1 = 0; a1 < L.length; a1++) if (L[a1].dim) order.push(a1)
            for (var a2 = 0; a2 < L.length; a2++) if (!L[a2].dim) order.push(a2)
            for (var oi = 0; oi < order.length; oi++) {
                var ln = L[order[oi]], pts = ln.pts
                g.globalAlpha = ln.dim ? 0.45 : 1
                g.strokeStyle = ch.lineColor(ln); g.lineWidth = ln.dim ? 1.4 : 2; g.lineJoin = "round"
                g.setLineDash(ln.shop === "t" ? [5, 4] : [])
                g.beginPath()
                for (var b = 0; b < pts.length; b++) { var px = X(pts[b][0]), py = Y(pts[b][1]); if (b) g.lineTo(px, py); else g.moveTo(px, py) }
                g.stroke()
                g.setLineDash([])
            }
            g.globalAlpha = 1
            if (hx >= left && hx <= right) {   // hover: date + prices
                var t = t0 + (hx - left) / (right - left) * span
                g.strokeStyle = Qt.rgba(1, 1, 1, 0.25); g.beginPath(); g.moveTo(hx, top); g.lineTo(hx, bottom); g.stroke()
                var label = new Date(t).toLocaleDateString(Qt.locale(), "dd.MM.yyyy")
                for (var c2 = 0; c2 < L.length; c2++) {
                    var best = null
                    for (var d = 0; d < L[c2].pts.length; d++) if (!best || Math.abs(L[c2].pts[d][0] - t) < Math.abs(best[0] - t)) best = L[c2].pts[d]
                    if (best) {
                        g.fillStyle = ch.lineColor(L[c2]); g.beginPath(); g.arc(X(best[0]), Y(best[1]), 3.5, 0, 6.3); g.fill()
                        label += "   " + L[c2].name + " " + best[1].toFixed(2).replace(".", ",") + " €"
                    }
                }
                g.fillStyle = T.text; g.font = "11px " + T.font; g.textAlign = "right"
                g.fillText(label, right, 26)
            }
        }
        HoverHandler {
            onPointChanged: ch.hx = point.position.x
            onHoveredChanged: if (!hovered) ch.hx = -1
        }
    }
}
