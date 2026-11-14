// Wish card hit on the scan page (0.9.9, Oliver via Gordon 14.11.2026; scanner/wishbar.py has the texts).
// A glass bar at the top of the camera image, headed by Orbit's sign + "Orbit": the own lists' line (· Undo or
// · Details) and the friends' line (· Details). Drag it anywhere – the place is kept (0–1 of the page); no ✕, it can't
// be closed: it dims after dimMs and stays; the next hit (new serial) replaces it and lights it up again.
// Details: a second glass bar (det), its own place – each list with its own Undo, or every friend.
import QtQuick

Item {
    id: wb
    property var wish: ({})                 // scanView.wish
    property var sp                         // scanView (wishUndo, wishPos, setWishPos)
    readonly property bool on: !!wish && wish.serial !== undefined
    property bool dim: false
    property string details: ""             // "" · "lists" · "friends"
    property var blockers: []               // the tiles: the first place cuts none of them (lead 14.11.)
    anchors.fill: parent
    visible: on

    onWishChanged: {
        if (!on) return
        if (wish.serial !== lastSerial) {   // a new hit: bright again, Details closed
            lastSerial = wish.serial
            dim = false; details = ""
            dimT.interval = wish.dimMs || 8000; dimT.restart()
            Qt.callLater(wb.replace)
        }
    }
    onWidthChanged: Qt.callLater(wb.replace)
    onHeightChanged: Qt.callLater(wb.replace)
    onDetailsChanged: if (details !== "") Qt.callLater(function () { wb.place(det, "details", det.fx, det.fy) })
    function replace() {   // window size changed or a new hit: both bars to their kept places
        if (wb.width <= 0 || !wb.on) return
        if (!bar.dragging) wb.place(bar, "bar", bar.fx, bar.fy)
        if (det.visible && !det.dragging) wb.place(det, "details", det.fx, det.fy)
    }
    property int lastSerial: -1
    Timer { id: dimT; interval: 8000; onTriggered: wb.dim = true }

    function place(card, which, fx, fy) {   // the kept place, else the first free one (freeSpot)
        var p = wb.sp ? wb.sp.wishPos(which) : []
        if (p.length === 2) {
            card.x = Math.max(0, Math.min(wb.width - card.width, p[0] * wb.width - card.width / 2))
            card.y = Math.max(0, Math.min(wb.height - card.height, p[1] * wb.height))
            return
        }
        var from = which === "bar" ? fy * wb.height : bar.y + bar.height + 8   // Details: below the bar
        var at = freeSpot(card.width, card.height, from, which === "bar" ? [] : [bar])
        card.x = at.x; card.y = at.y
    }
    // The first place from the top (from y0 on) where a w×h bar cuts no tile: in each band the free gaps between the
    // tiles, the one nearest the middle, the bar centred in it (as far as it fits). Nothing free: centred at y0.
    function freeSpot(w, h, y0, extra) {
        var m = 8, rects = [], i
        var all = (wb.blockers || []).concat(extra || [])
        for (i = 0; i < all.length; i++) {
            var t = all[i]
            if (t && t.visible && t.width > 0 && t.height > 0) {
                var q = t.mapToItem(wb, 0, 0)
                rects.push({x: q.x - m, y: q.y - m, r: q.x + t.width + m, b: q.y + t.height + m})
            }
        }
        var mid = wb.width / 2, lo = 12, hi = wb.width - 12
        for (var y = Math.max(0, y0); y + h <= wb.height * 0.75; y += 6) {
            var cuts = rects.filter(function (r) { return r.y < y + h && r.b > y })
                            .sort(function (a, b) { return a.x - b.x })
            var gaps = [], x = lo
            for (i = 0; i < cuts.length; i++) {
                if (cuts[i].x > x) gaps.push([x, cuts[i].x])
                x = Math.max(x, cuts[i].r)
            }
            if (hi > x) gaps.push([x, hi])
            var best = null
            for (i = 0; i < gaps.length; i++) {
                var g = gaps[i]
                if (g[1] - g[0] < w) continue
                var cx = Math.max(g[0], Math.min(g[1] - w, mid - w / 2))   // as central as the gap lets it
                if (best === null || Math.abs(cx + w / 2 - mid) < Math.abs(best + w / 2 - mid)) best = cx
            }
            if (best !== null) return {x: best, y: y}
        }
        return {x: Math.max(0, mid - w / 2), y: Math.max(0, Math.min(wb.height - h, y0))}
    }
    function keep(card, which) {
        if (wb.sp) wb.sp.setWishPos(which, (card.x + card.width / 2) / wb.width, card.y / wb.height)
    }

    component Link: Text {
        id: lk
        property string kind: ""
        signal hit()
        visible: text !== ""
        color: kind === "" ? T.text2 : (lkMa.containsMouse ? "#ffffff" : T.top)
        font.family: T.font; font.pixelSize: 13; font.bold: kind !== ""; font.underline: kind !== "" && lkMa.containsMouse
        MouseArea { id: lkMa; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; enabled: lk.kind !== ""
                    cursorShape: Qt.PointingHandCursor; onClicked: lk.hit() }
    }
    component Glass: Rectangle {
        id: gl
        property string which
        property real fx: 0.5
        property real fy: 0.0
        radius: 12
        color: Qt.rgba(0.06, 0.06, 0.065, 0.9)
        border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.16)
        opacity: wb.dim ? 0.45 : 1
        Behavior on opacity { NumberAnimation { duration: 600 } }
        readonly property bool dragging: glMa.drag.active
        MouseArea {
            id: glMa   // drag anywhere on the glass (the links lie above and still click)
            anchors.fill: parent; cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
            drag.target: gl; drag.minimumX: 0; drag.minimumY: 0
            drag.maximumX: wb.width - gl.width; drag.maximumY: wb.height - gl.height
            onReleased: wb.keep(gl, gl.which)
        }
        onWidthChanged: if (!dragging) Qt.callLater(wb.replace)
    }

    Glass {
        id: bar
        which: "bar"; fx: 0.5; fy: 0.025
        width: Math.min(wb.width - 24, Math.max(head.implicitWidth, line1.implicitWidth, line2.implicitWidth) + 32)
        height: col.height + 20
        Column {
            id: col
            x: 16; y: 10; spacing: 5
            Row {
                id: head; spacing: 6
                NavIcon { key: "orbit"; s: 0.7; color: T.text2; anchors.verticalCenter: parent.verticalCenter }
                Text { text: wb.wish.head || "Orbit"; color: T.text2; font.family: T.font; font.pixelSize: 12
                       font.letterSpacing: 0.6; anchors.verticalCenter: parent.verticalCenter }
            }
            Row {
                id: line1; spacing: 0; visible: (wb.wish.text || "") !== ""
                Text { text: wb.wish.text || ""; color: "#ededed"; font.family: T.font; font.pixelSize: 14; font.bold: true }
                Text { visible: (wb.wish.link || "") !== ""; text: "  ·  "; color: T.text2; font.family: T.font; font.pixelSize: 13
                       anchors.baseline: parent.children[0].baseline }
                Link { text: wb.wish.link || ""; kind: wb.wish.linkKind || ""
                       anchors.baseline: parent.children[0].baseline
                       onHit: kind === "undo" ? wb.sp.wishUndo("")
                                              : (wb.details = wb.details === "lists" ? "" : "lists") }
            }
            Row {
                id: line2; spacing: 0; visible: (wb.wish.friendText || "") !== ""
                Text { text: wb.wish.friendText || ""; color: "#d6d6d6"; font.family: T.font; font.pixelSize: 13 }
                Text { visible: (wb.wish.friendLink || "") !== ""; text: "  ·  "; color: T.text2; font.family: T.font
                       font.pixelSize: 13; anchors.baseline: parent.children[0].baseline }
                Link { text: wb.wish.friendLink || ""; kind: "details"; anchors.baseline: parent.children[0].baseline
                       onHit: wb.details = wb.details === "friends" ? "" : "friends" }
            }
        }
    }

    Glass {   // Details: every own list (each with its Undo) or every friend looking for the card
        id: det
        which: "details"; fx: 0.5; fy: 0.16
        visible: wb.details !== ""
        width: Math.min(wb.width - 24, Math.max(320, detCol.implicitWidth + 32))
        height: detCol.height + 22
        Column {
            id: detCol
            x: 16; y: 11; spacing: 7
            Text { text: wb.details === "lists" ? (wb.wish.listsTitle || "") : (wb.wish.friendsTitle || "")
                   color: T.text2; font.family: T.font; font.pixelSize: 12; font.letterSpacing: 0.4 }
            Repeater {
                model: wb.details === "lists" ? (wb.wish.lists || []) : []
                Row {
                    required property var modelData
                    spacing: 0
                    Text { text: modelData.name + (modelData.n > 1 ? "  ×" + modelData.n : ""); font.family: T.font
                           font.pixelSize: 13; color: modelData.undone ? T.text2 : "#ededed" }
                    Text { visible: modelData.link !== ""; text: "  ·  "; color: T.text2; font.family: T.font; font.pixelSize: 13 }
                    Link { text: modelData.link; kind: modelData.undone ? "" : "undo"
                           onHit: wb.sp.wishUndo(modelData.id) }
                    Text { visible: (modelData.note || "") !== ""; text: "  ·  " + modelData.note; color: T.text2
                           font.family: T.font; font.pixelSize: 12 }
                }
            }
            Repeater {
                model: wb.details === "friends" ? (wb.wish.friends || []) : []
                Row {
                    required property var modelData
                    spacing: 0
                    Text { text: modelData.name; font.family: T.font; font.pixelSize: 13; font.bold: true; color: "#ededed" }
                    Text { visible: modelData.lists !== ""; text: "  ·  " + modelData.lists; color: T.text2
                           font.family: T.font; font.pixelSize: 13 }
                }
            }
        }
    }
}
