// Group by (Oliver, 29.10.): the strip under the head of the Library – no pop-up, it slides open in place.
// Top: (nothing grouped yet) the properties to start with, the saved groupings as chips (up to 5), ☆ saves the chain.
// Then the breadcrumbs, each above its column of the tree (Oliver, 30.10.: a thin line in the gaps, no arrows), and
// after a divider "Ungroup" (the real reset) and the switch "Active" (off = the normal list, the path stays; state by
// brightness). The chips with the numbers are in the chip row (GroupChips.qml).
// Below: the tree from left to right – curved lines, their width grows with the share of the cards.
// Only the bright path fans out; its nodes are lit, all others dimmed – every node shows its number. A click on a node
// shows its cards in the grid (a dimmed one jumps across, a lit one goes back there); at the end of the path
// "Branch on by …" lets new branches grow. Logic: lib.group (ui/qgroup.py, ui/grouping.py).
import QtQuick

Item {
    id: gp
    property var g                         // lib.group
    readonly property bool open: g ? g.open : false
    readonly property real rowH: 34        // a node with its gap
    readonly property real colW: 210       // a level
    readonly property real treeH: Math.min(380, Math.max(130, lay.h + 32))
    readonly property real crumbH: g && g.active ? 30 : 0
    readonly property var crumbList: g ? g.levels.filter(function (l) { return !g.on || l.col >= 0 }) : []
    readonly property real fullH: top.height + 12 + crumbH + (crumbH > 0 ? 8 : 0) + (g && g.active && !g.on ? 40 : treeH) + 10
    property real openH: open ? fullH : 0
    Behavior on openH { NumberAnimation { id: openAnim; duration: 300 * shell.speed; easing.type: Easing.OutCubic } }
    readonly property bool animating: openAnim.running
    readonly property real targetH: open ? fullH : 0
    height: openH
    clip: true
    visible: height > 0.5

    // ---------- layout of the tree (columns, y of every node) – from the tree the backend counted ----------
    readonly property var lay: {
        var t = g ? g.tree : null, cols = t ? t.cols : [], out = {cols: [], h: rowH, rootY: 0}
        var maxN = 1
        for (var d = 0; d < cols.length; d++) maxN = Math.max(maxN, cols[d].nodes.length + (cols[d].hidden > 0 || cols[d].all > 9 ? 1 : 0))
        var nextN = t && t.next ? t.next.length + 1 : 0
        var H = Math.max(maxN, nextN, 1) * rowH
        out.h = H
        var parentY = H / 2
        out.rootY = parentY
        for (var c = 0; c < cols.length; c++) {
            var n = cols[c].nodes.length + (cols[c].hidden > 0 || cols[c].all > 9 ? 1 : 0)
            var y0 = Math.max(0, Math.min(H - n * rowH, parentY - n * rowH / 2))
            var ys = [], lit = -1
            for (var i = 0; i < cols[c].nodes.length; i++) { ys.push(y0 + i * rowH + rowH / 2); if (cols[c].nodes[i].on) lit = i }
            out.cols.push({y0: y0, ys: ys, lit: lit, parentY: parentY, moreY: y0 + cols[c].nodes.length * rowH + rowH / 2})
            if (lit < 0) break
            parentY = ys[lit]
        }
        out.nextY0 = Math.max(0, Math.min(H - nextN * rowH, parentY - nextN * rowH / 2))
        out.leafY = parentY
        return out
    }

    // ---------- top row: chain · saved · save ----------
    Item {
        id: top
        y: 4; width: parent.width; height: 34
        Row {
            id: chainRow
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Text { anchors.verticalCenter: parent.verticalCenter
                   text: gp.g && gp.g.active ? shell.text("Grouped by") : shell.text("Group by")
                   color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
            Text { visible: !!gp.g && gp.g.active; anchors.verticalCenter: parent.verticalCenter
                   text: gp.g ? gp.g.chain.map(function (c) { return c.label }).join("  ·  ") : ""
                   color: T.muted; font.family: T.font; font.pixelSize: 13 }
            Repeater {   // nothing grouped yet: start with a property
                model: gp.g && gp.g.chain.length === 0 ? gp.g.keys : []
                Btn { required property var modelData
                      height: 30; compact: true; text: modelData.label; onClicked: gp.g.addLevel(modelData.key) }
            }
        }
        Row {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            Repeater {   // saved groupings: the first five as chips
                model: gp.g ? gp.g.saved : []
                Btn { required property var modelData
                      required property int index
                      visible: modelData.chip
                      height: 30; compact: true; led: true; active: modelData.on; text: modelData.name
                      tip: shell.text("Saved grouping – click: use it")
                      onClicked: gp.g.useSaved(index) }
            }
            Btn { visible: !!gp.g && gp.g.active; height: 30; width: 36; compact: true
                  navIcon: gp.g && gp.g.isSaved ? "starOn" : "star"
                  tip: gp.g && gp.g.isSaved ? shell.text("Saved – click: forget this grouping")
                                            : shell.text("Save this grouping")
                  onClicked: gp.g.toggleSave() }
        }
    }

    // ---------- breadcrumbs: each above its column (moving with the tree) · divider · Ungroup · switch ----------
    Item {
        id: crumbs
        y: top.y + top.height + 12
        width: parent.width; height: gp.crumbH
        visible: height > 0
        Item {   // the crumbs, clipped left of the divider
            id: crumbArea
            width: tools.x - 14; height: parent.height
            clip: true
            Repeater {
                // a level switched off has no column: it stays grey in the chip row (with "Enable") – here only the
                // levels with a column; with the whole grouping off all of them, grey, side by side
                model: gp.crumbList
                Item {
                    id: crumb
                    required property var modelData
                    required property int index
                    // above its column; a level without a column (switched off / grouping off) lines up after the
                    // previous one
                    readonly property real colX: canvasBox.x0 + (gp.g.on ? modelData.col : index) * gp.colW
                    x: colX - fl.contentX
                    width: gp.colW - 50; height: parent.height
                    Rectangle {   // the branch to the next crumb: a thin line in the gap
                        visible: crumb.index < gp.crumbList.length - 1
                        x: cb.width + 4; width: gp.colW - cb.width - 8
                        anchors.verticalCenter: parent.verticalCenter; height: 1; color: T.line2
                    }
                    Rectangle {
                        id: cb
                        anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(crumb.width, ct.implicitWidth + 24); height: 26; radius: 13
                        readonly property bool grey: crumb.modelData.grey
                        color: cbh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent"
                        border.width: 1; border.color: crumb.modelData.picked && !grey ? T.text2 : T.line2
                        opacity: grey ? 0.45 : 1
                        Text { id: ct; anchors.centerIn: parent; width: Math.min(implicitWidth, crumb.width - 24)
                               elide: Text.ElideRight
                               text: crumb.modelData.picked ? crumb.modelData.label : crumb.modelData.level
                               color: crumb.modelData.picked ? T.text : T.muted
                               font.family: T.font; font.pixelSize: 12; font.bold: crumb.modelData.picked }
                        HoverHandler { id: cbh; cursorShape: Qt.PointingHandCursor
                            onHoveredChanged: if (hovered) {
                                var q = cb.mapToItem(null, cb.width / 2, cb.height + 2)
                                shell.tip(crumb.modelData.level + (crumb.modelData.picked ? " · " + crumb.modelData.label : "")
                                          + "\n" + shell.text("Click: back to this level"), q.x, q.y)
                            } else shell.tip("", 0, 0) }
                        TapHandler { onTapped: { shell.tip("", 0, 0)
                            if (crumb.modelData.disabled) gp.g.toggleLevel(crumb.modelData.i)
                            else if (crumb.modelData.picked) gp.g.toLevel(crumb.modelData.i)
                            else gp.g.toRoot() } }
                    }
                }
            }
        }
        Row {
            id: tools
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Rectangle { width: 1; height: 22; color: T.line2; anchors.verticalCenter: parent.verticalCenter }   // divider
            Btn { height: 30; compact: true; text: shell.text("Ungroup")
                  tip: shell.text("The library as before – the saved groupings stay"); onClicked: gp.g.clear() }
            Btn { height: 30; compact: true; led: true; active: !!gp.g && gp.g.on; text: shell.text("Active")
                  tip: gp.g && gp.g.on ? shell.text("On – click: the normal list, the path stays")
                                       : shell.text("Off – click: group again")
                  onClicked: gp.g.setOn(!gp.g.on) }
        }
    }
    Text {   // the whole grouping off: the normal list, the path stays
        visible: !!gp.g && gp.g.active && !gp.g.on
        y: crumbs.y + crumbs.height + 12; x: 2
        text: shell.text("Grouping is off – the library shows the normal list, the path stays.")
        color: T.muted; font.family: T.font; font.pixelSize: 13
    }

    // ---------- the tree ----------
    Flickable {
        id: fl
        y: crumbs.y + crumbs.height + (crumbs.height > 0 ? 8 : 0)
        width: parent.width; height: gp.treeH
        contentWidth: Math.max(width, rootBox.width + 40 + ((gp.g ? gp.g.tree.cols.length : 0) + 1) * gp.colW + 260)
        contentHeight: Math.max(height, gp.lay.h + 14)
        clip: true; boundsBehavior: Flickable.StopAtBounds
        visible: !!gp.g && gp.g.active && gp.g.on
        Item {
            id: canvasBox
            y: 6; width: fl.contentWidth; height: gp.lay.h
            readonly property real x0: rootBox.width + 40   // where level 0 begins
            Canvas {   // the lines: drawn once per tree (not per frame)
                id: lines
                anchors.fill: parent
                renderStrategy: Canvas.Cooperative
                Connections { target: gp.g; function onTreeChanged() { lines.requestPaint() } }
                Connections { target: gp; function onLayChanged() { lines.requestPaint() } }
                onAvailableChanged: if (available) requestPaint()
                readonly property color ink: T.text
                onPaint: {
                    var c = getContext("2d"); c.reset()
                    var t = gp.g ? gp.g.tree : null; if (!t) return
                    var px = rootBox.width   // the right edge of the parent node
                    for (var d = 0; d < gp.lay.cols.length; d++) {
                        var col = gp.lay.cols[d], nodes = t.cols[d].nodes
                        var x1 = canvasBox.x0 + d * gp.colW
                        var top = 0   // width 1 … 6 px, measured against the biggest branch of the level
                        for (var j = 0; j < nodes.length; j++) top = Math.max(top, nodes[j].share)
                        for (var i = 0; i < nodes.length; i++) {
                            var bright = nodes[i].on || col.lit < 0
                            c.strokeStyle = Qt.rgba(ink.r, ink.g, ink.b, nodes[i].on ? 0.85 : (bright ? 0.4 : 0.16))
                            c.lineWidth = 1 + 5 * (top > 0 ? nodes[i].share / top : 0)
                            c.lineCap = "round"
                            c.beginPath(); c.moveTo(px, col.parentY)
                            var mx = (px + x1) / 2
                            c.bezierCurveTo(mx, col.parentY, mx, col.ys[i], x1, col.ys[i]); c.stroke()
                        }
                        if (col.lit < 0) return
                        px = x1 + gp.colW - 50   // the lit node's right edge (nodes are colW - 50 wide)
                    }
                    if (t.next && t.next.length) {   // dashed: where it could branch on
                        c.setLineDash([3, 4]); c.lineWidth = 1.2
                        c.strokeStyle = Qt.rgba(ink.r, ink.g, ink.b, 0.3)
                        var xn = canvasBox.x0 + gp.lay.cols.length * gp.colW
                        for (var k = 0; k < t.next.length; k++) {
                            var yk = gp.lay.nextY0 + (k + 1) * gp.rowH + gp.rowH / 2
                            c.beginPath(); c.moveTo(px, gp.lay.leafY)
                            var m2 = (px + xn) / 2
                            c.bezierCurveTo(m2, gp.lay.leafY, m2, yk, xn, yk); c.stroke()
                        }
                    }
                }
            }
            // root: the whole (search/filters still apply)
            Rectangle {
                id: rootBox
                x: 0; y: gp.lay.rootY - height / 2
                width: rootT.implicitWidth + 24; height: 28; radius: 14
                readonly property bool lit: !!gp.g && gp.g.tree.path.length === 0
                color: lit ? T.surface2 : "transparent"
                border.width: 1; border.color: lit ? T.text2 : T.line2
                Text { id: rootT; anchors.centerIn: parent
                       text: shell.text("All") + "  " + (gp.g ? gp.g.tree.root.cards : 0)
                       color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
                HoverHandler { id: rth; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: gp.g.toRoot() }
            }
            Repeater {   // the levels
                model: gp.g ? gp.g.tree.cols : []
                Item {
                    id: colItem
                    required property var modelData
                    required property int index
                    readonly property var cl: gp.lay.cols[index] || {ys: [], y0: 0, moreY: 0}
                    x: canvasBox.x0 + index * gp.colW; width: gp.colW - 50; height: canvasBox.height
                    visible: index < gp.lay.cols.length
                    Repeater {
                        model: colItem.modelData.nodes
                        Rectangle {
                            id: node
                            required property var modelData
                            required property int index
                            y: (colItem.cl.ys[index] || 0) - height / 2
                            width: colItem.width; height: 28; radius: 14
                            readonly property bool lit: modelData.on
                            readonly property bool fanned: colItem.cl.lit < 0   // a level nothing is picked in yet
                            opacity: lit || fanned ? 1 : (nh.hovered ? 0.85 : 0.5)
                            Behavior on opacity { NumberAnimation { duration: 140 } }
                            color: lit ? T.surface2 : (nh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent")
                            border.width: 1; border.color: lit ? T.text : T.line2
                            scale: 1
                            Text { x: 12; anchors.verticalCenter: parent.verticalCenter; width: parent.width - cnt.width - 30
                                   elide: Text.ElideRight; text: node.modelData.label
                                   color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: node.lit }
                            Text { id: cnt; anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                   text: node.modelData.cards; color: node.lit ? T.text : T.text2
                                   font.family: T.font; font.pixelSize: 12; font.bold: true }
                            HoverHandler { id: nh; cursorShape: Qt.PointingHandCursor
                                onHoveredChanged: if (hovered) {
                                    var q = node.mapToItem(null, node.width / 2, node.height + 2)
                                    shell.tip(node.modelData.label + " · " + node.modelData.cards + " · " + node.modelData.valueText
                                              + "\n" + (node.lit ? shell.text("Click: back to here") : shell.text("Click: show these cards")), q.x, q.y)
                                } else shell.tip("", 0, 0) }
                            TapHandler { onTapped: { shell.tip("", 0, 0); gp.g.pick(colItem.index, node.modelData.v) } }
                            SequentialAnimation {   // zoom into the picked node (review: transition "Zoom")
                                id: zoom
                                NumberAnimation { target: node; property: "scale"; to: 1.12; duration: 120 * shell.speed; easing.type: Easing.OutCubic }
                                NumberAnimation { target: node; property: "scale"; to: 1; duration: 220 * shell.speed; easing.type: Easing.OutBack }
                            }
                            Connections { target: gp.g
                                function onJumped(d) { if (d === colItem.index && node.lit && shell.animate) zoom.restart() } }
                        }
                    }
                    Text {   // "+ n more" / "− show fewer"
                        visible: colItem.modelData.hidden > 0 || colItem.modelData.all > 9
                        x: 12; y: colItem.cl.moreY - height / 2
                        text: colItem.modelData.hidden > 0 ? "+ " + shell.text("%1 more").arg(colItem.modelData.hidden)
                                                           : "− " + shell.text("show fewer")
                        color: mh.hovered ? T.text : T.muted; font.family: T.font; font.pixelSize: 12
                        HoverHandler { id: mh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: gp.g.showAll(colItem.index) }
                    }
                }
            }
            // at the end of the bright path: branch on by …
            Item {
                visible: !!gp.g && gp.g.tree.next.length > 0
                x: canvasBox.x0 + gp.lay.cols.length * gp.colW; y: gp.lay.nextY0
                width: 240; height: (gp.g ? gp.g.tree.next.length + 1 : 1) * gp.rowH
                Text { y: gp.rowH / 2 - height / 2; text: shell.text("Branch on by …")
                       color: T.dim; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1
                       font.capitalization: Font.AllUppercase }
                Repeater {
                    model: gp.g ? gp.g.tree.next : []
                    Rectangle {
                        required property var modelData
                        required property int index
                        y: (index + 1) * gp.rowH + gp.rowH / 2 - height / 2
                        width: nxT.implicitWidth + 24; height: 28; radius: 14
                        color: xh.hovered ? Qt.lighter(T.surface, 1.1) : "transparent"
                        border.width: 1; border.color: xh.hovered ? T.text2 : T.line
                        Text { id: nxT; anchors.centerIn: parent
                               text: modelData.label + "  ·  " + shell.text("%1 branches").arg(modelData.branches)
                               color: xh.hovered ? T.text : T.text2; font.family: T.font; font.pixelSize: 12 }
                        HoverHandler { id: xh; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: gp.g.addLevel(modelData.key) }
                    }
                }
            }
        }
    }
    Text {   // grouping only applies to your own cards
        visible: !!gp.g && !gp.g.enabled
        y: top.y + top.height + 20; x: 2
        text: shell.text("Group by works in “My Collection”.")
        color: T.muted; font.family: T.font; font.pixelSize: 13
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line; visible: gp.height > 2 }
}
