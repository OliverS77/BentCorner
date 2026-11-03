// The tiles of the scan page (ui/scantiles.py) in their grid between the two bars: the scan (the log and its cards in
// one tile), last hit, biggest hit, status line, stats. Every tile shows more or less depending on its size, never
// less than its purpose needs (the scan tile always keeps "End scan"). Inside no boxes – fine lines, size and weight
// only (design rule). The grid's dots show only while moving/resizing or while the tile drawer is open.
import QtQuick

Item {
    id: g
    property bool chrome: true             // the mouse moved lately: the tiles' keys and grips are there
    property bool arrangeMode: false       // the tile drawer is open: grid visible
    property bool arranging: false         // a tile is being moved/resized right now
    property var stage: ({})               // scanView.scanStage
    signal drawerWanted()                  // a tile's drawer key
    readonly property var tb: scanTiles
    readonly property var lay: tb.layout
    readonly property var s: tb.session
    readonly property var vw: tb.view
    readonly property real fz: 1.15        // the tiles' type: a bit bigger than the rest of the app (Oliver)
    // the tiles' tint over the frosted camera image: darker the brighter the image (scanView.frostLum 0…1) – small grey
    // text stays readable on a bright desk or room too
    readonly property real tint: Math.max(T.tile.glass, Math.min(0.85, T.tile.glass + (scanView.frostLum - 0.3) * 0.6))
    readonly property int cols: tb.grid.cols
    readonly property int rows: tb.grid.rows
    readonly property real x0: T.tile.margin
    readonly property real y0: T.tile.bar + T.tile.margin
    readonly property real cw: (width - 2 * T.tile.margin) / cols
    readonly property real ch: (height - 2 * T.tile.bar - 2 * T.tile.margin) / rows
    // ---- what each tile's content needs (pixels): never smaller than its purpose needs, never bigger than there is
    // to show. One row (S) where it keeps its purpose; taller than one row, at least as tall as the medium content.
    readonly property real hd: T.tile.head + T.tile.padB
    readonly property real rowH: T.tile.row + 8
    // scan tile: name + meta, one part head, one card, the foot (search field, End scan) – it scrolls inside
    readonly property real footH: 34 + 8 + 46 + 4
    readonly property real scanMin: hd + 30 + 21 + 30 + rowH + footH
    // the free strip for the preview of a list card (overlay_paint._beside_list): below the status tile when it sits
    // up top, above the dock (the grid ends a bar's height above the bottom)
    readonly property real freeTop: tStatus.visible && tStatus.y < height / 2 ? tStatus.y + tStatus.height : y0
    readonly property real freeBottom: height - T.tile.bar
    onFreeTopChanged: scanView.setFreeBand(freeTop, freeBottom)
    onFreeBottomChanged: scanView.setFreeBand(freeTop, freeBottom)
    // a hit tile's large form: the card on top, name, set and price below – as tall as that is at the tile's
    // (stored) width
    readonly property real hitTextH: 104
    function hitMaxH(k) {
        var e = lay[k] || ({w: 4})
        var w = Math.min(e.w * cw - T.tile.gap, 560) - 2 * T.tile.pad
        return hd + hitTextH + Math.max(150, Math.min(w, 320) / 0.716)
    }
    readonly property var need: ({
        "session": {minW: 320, maxW: 820, midH: scanMin, maxH: 4000, noRow: true},
        "hit": {minW: 260, maxW: 560, midH: hd + 80, maxH: hitMaxH("hit")},
        "top": {minW: 260, maxW: 560, midH: hd + 80, maxH: hitMaxH("top")},
        // status: one row = the chain; taller = the chain, what it does, the card it is on
        "status": {minW: 470, maxW: 640, midH: hd + 58, maxH: hd + 58},
        // stats: no one-row form – at least the figures and one chart
        "stats": {minW: 340, maxW: 1040, midH: hd + 40 + 96 + 120, maxH: hd + Math.max(260, statsH), noRow: true}
    })
    property real statsH: 0                // the stats' content height (charts) – set by the tile
    readonly property var tiles: [tSession, tHit, tTop, tStatus, tStats]
    function tileOf(k) { for (var i = 0; i < tiles.length; i++) if (tiles[i].key === k) return tiles[i]; return null }
    function cellsW(px) { return Math.max(2, Math.ceil((px + T.tile.gap) / cw)) }
    function cellsH(px) { return Math.max(1, Math.ceil((px + T.tile.gap) / ch)) }
    // -> {minW, maxW, minH, midH, maxH} in cells (ScanTile clamps to it while resizing)
    function lim(k) {
        var n = need[k]
        var minW = cellsW(n.minW)
        var midH = n.midH > 0 ? cellsH(n.midH) : 1
        return {minW: minW, maxW: Math.max(minW, cellsW(n.maxW)), minH: n.noRow ? midH : 1,
                midH: midH, maxH: n.maxH > 0 ? Math.max(midH, cellsH(n.maxH)) : 1}
    }
    // a height in cells -> the nearest allowed one: 1 row, or medium content and up
    function snapH(k, h) {
        var l = lim(k)
        if (h <= l.minH || l.midH <= 1) return Math.max(l.minH, Math.min(h, l.maxH))
        if (h < l.midH) return h < (1 + l.midH) / 2 ? 1 : l.midH
        return Math.min(h, l.maxH)
    }
    // the content's size of a tile: S one row, L as soon as the large content fits, else M
    function sizeOf(t, largePx) { return t.ent.h <= 1 ? "S" : t.height >= largePx - 2 ? "L" : "M" }

    // ---- the grid (only while arranging): quiet dots where its lines would cross ----
    Canvas {
        id: lines
        x: g.x0 - 2; y: g.y0 - 2; width: g.cw * g.cols + 4; height: g.ch * g.rows + 4
        visible: g.arranging || g.arrangeMode
        onWidthChanged: requestPaint(); onHeightChanged: requestPaint()
        onPaint: {
            var c = getContext("2d"); c.reset()
            c.fillStyle = "rgba(255,255,255,0.38)"
            for (var i = 0; i <= g.cols; i++)
                for (var j = 0; j <= g.rows; j++) {
                    c.beginPath(); c.arc(Math.round(i * g.cw) + 2, Math.round(j * g.ch) + 2, 1.3, 0, 2 * Math.PI); c.fill()
                }
        }
    }
    // where the tile in hand will land
    Rectangle {
        id: ghost
        property var t: {
            for (var i = 0; i < g.tiles.length; i++) if (g.tiles[i].moving || g.tiles[i].sizing) return g.tiles[i]
            return null
        }
        visible: t !== null
        x: t ? g.x0 + (t.moving ? t.tc : t.ent.c) * g.cw + T.tile.gap / 2 : 0
        y: t ? g.y0 + (t.moving ? t.trow : t.ent.r) * g.ch + T.tile.gap / 2 : 0
        width: t ? (t.sizing ? t.tw : t.sw) * g.cw - T.tile.gap : 0
        height: t ? (t.sizing ? t.th : t.sh) * g.ch - T.tile.gap : 0
        radius: T.tile.radius
        color: Qt.rgba(1, 1, 1, 0.05)
        border.width: 2; border.color: Qt.rgba(1, 1, 1, 0.7)
        Rectangle {   // size label while resizing
            visible: ghost.t !== null && ghost.t.sizing
            anchors.horizontalCenter: parent.horizontalCenter; anchors.top: parent.bottom; anchors.topMargin: 8
            width: szT.implicitWidth + 16; height: 22; radius: 6; color: "#ffffff"
            Text { id: szT; anchors.centerIn: parent; color: "#000000"; font.family: T.font; font.pixelSize: Math.round(12 * g.fz); font.bold: true
                   text: ghost.t ? ghost.t.tw + " × " + ghost.t.th : "" }
        }
    }

    component Line: Rectangle { width: parent ? parent.width : 0; height: T.tile.line; color: Qt.rgba(1, 1, 1, 0.09) }
    component Key2: Text {   // a quiet text action in a tile (no key box inside a box)
        id: k2
        property bool strong: false
        signal clicked()
        color: !enabled ? T.dim : strong ? T.top : (ma.containsMouse ? T.text : T.text2)
        font.family: T.font; font.pixelSize: Math.round(13 * g.fz); font.bold: strong
        MouseArea { id: ma; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    enabled: k2.enabled; onClicked: k2.clicked() }
    }
    component Fact: Item {
        property string label
        property alias value: v.text
        property bool big: false
        width: parent ? parent.width : 0; height: big ? 40 : 32
        Line { anchors.top: parent.top }
        Text { anchors.verticalCenter: parent.verticalCenter; text: parent.label; color: T.muted; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
        Text { id: v; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
               color: parent.big ? T.top : T.text; font.family: parent.big ? T.display : T.font; font.pixelSize: Math.round((parent.big ? 22 : 15) * g.fz)
               font.weight: parent.big ? Font.DemiBold : Font.Normal }
    }
    component Thumb: Item {
        id: th
        property string src
        property int res: 160          // how finely the image is decoded (the big hit card: more)
        signal shown()                 // the new picture is on screen (decoded) – or there is none
        readonly property bool settled: src === "" || (next.status === Image.Ready && im.source == next.source)
        // a new picture is decoded aside first; the one on screen stays until then (no gap, no "no image" flash)
        Image { id: im; anchors.fill: parent; fillMode: Image.PreserveAspectCrop; cache: true
                sourceSize.width: th.res; smooth: true; mipmap: th.res > 160 }
        Image {
            id: next
            visible: false; asynchronous: true; cache: true; source: th.src; sourceSize.width: th.res
            onStatusChanged: if (status === Image.Ready || status === Image.Error) {
                im.source = status === Image.Ready ? source : ""; th.shown() }
        }
        onSrcChanged: if (src === "") { im.source = ""; shown() }
        NoImage { anchors.fill: parent; thumb: true; visible: im.status !== Image.Ready && next.status !== Image.Loading }
    }

    // ================= Scan (the log and its cards) =================
    // From the top: the name (empty = "Scan N") with the value and the number of cards; SETTINGS (folds) – every
    // setting of the log, edited where it stands (a click beside a field saves, Esc goes back); then ONE list of the
    // scan's cards, the newest on top (boosters: per pack). The foot stays: the card search and the biggest key of the
    // page, "End scan" (right away – "Undo" for a moment). No "Start": the first card starts it.
    readonly property var kinds: [{ k: "cards", t: shell.text("Cards") }, { k: "packs", t: shell.text("Boosters") },
                                  { k: "singles", t: shell.text("Singles") }]
    // cards / singles only while at most one pack is scanned (scanner/core.py can_cards)
    function kindCan(k) { return k === "packs" || g.s.canCards === true || g.s.kind === k }
    readonly property bool packs: g.s.kind === "packs"
    readonly property var cards: tb.cards
    property var packOpen: ({})            // boosters: packs opened / folded by hand (pack number -> open)
    property point lastPt: Qt.point(-1, -1)   // the mouse's last real position over the list (CardRow: preview)
    function secOpen(k) { return g.vw.sections ? g.vw.sections[k] !== false : true }
    property bool setInfo: false           // "Only these sets": the explanation folded open (ⓘ)

    component KindSwitch: Item {   // one segment key: three words, the lit one is on (selection = brightness)
        id: ks
        width: parent ? parent.width : 0; height: 38
        Row {
            anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 1
            width: parent.width; spacing: 2
            Repeater {
                model: g.kinds
                Rectangle {
                    id: seg
                    required property var modelData
                    readonly property bool on: g.s.kind === modelData.k
                    readonly property bool can: g.kindCan(modelData.k)
                    width: (ks.width - 4) / 3; height: 28; radius: 8
                    color: on ? Qt.rgba(1, 1, 1, 0.08) : "transparent"
                    border.width: 1; border.color: on ? Qt.rgba(1, 1, 1, 0.18) : "transparent"
                    opacity: can ? 1 : 0.4
                    Text { anchors.centerIn: parent; text: seg.modelData.t; font.family: T.font; font.pixelSize: Math.round(13 * g.fz)
                           font.bold: seg.on; color: seg.on ? T.top : (sm.containsMouse && seg.can ? T.text : T.muted) }
                    MouseArea {
                        id: sm
                        anchors.fill: parent; hoverEnabled: true
                        cursorShape: seg.can && !seg.on ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onPressed: forceActiveFocus()
                        onClicked: if (seg.can && !seg.on) g.tb.setKind(seg.modelData.k)
                        onContainsMouseChanged: if (!seg.can) containsMouse
                            ? shell.tip(shell.text("Only possible while at most one pack is scanned"),
                                        seg.mapToItem(null, seg.width / 2, seg.height).x, seg.mapToItem(null, 0, seg.height).y)
                            : shell.tip("", 0, 0)
                    }
                }
            }
        }
    }
    component FieldRow: Item {   // label on the left, the value (editable) on the right, a fine line above
        id: fr
        property string label
        property string tip: ""      // what the field does – on the label, under the mouse
        default property alias value: slot.data
        width: parent ? parent.width : 0; height: 32
        Line { anchors.top: parent.top }
        Text { id: frL; anchors.verticalCenter: parent.verticalCenter; text: parent.label; color: T.muted; font.family: T.font; font.pixelSize: Math.round(13 * g.fz)
               HoverHandler { enabled: fr.tip !== ""
                              onHoveredChanged: hovered ? shell.tip(fr.tip, frL.mapToItem(null, frL.width / 2, frL.height).x,
                                                                    frL.mapToItem(null, 0, frL.height).y)
                                                        : shell.tip("", 0, 0) } }
        Item { id: slot; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
               width: parent.width - 90; height: parent.height }
    }
    component Pick: Text {   // a value chosen from a menu: reads like text, "›" says there is a choice
        signal clicked()
        anchors.right: parent ? parent.right : undefined; anchors.verticalCenter: parent ? parent.verticalCenter : undefined
        color: pm.containsMouse ? T.top : T.text; font.family: T.font; font.pixelSize: Math.round(14 * g.fz)
        MouseArea { id: pm; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onPressed: forceActiveFocus(); onClicked: parent.clicked() }
    }
    // a part's head: its name (a click folds it), a short summary on the right
    component SecHead: Item {
        id: sh
        property string key
        property string label
        property string summary: ""
        readonly property bool open: g.secOpen(key)
        width: parent ? parent.width : 0; height: 30
        Line { anchors.top: parent.top }
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: 6
            Chevron { anchors.verticalCenter: parent.verticalCenter; open: sh.open; size: 12; color: T.muted }
            Text { anchors.verticalCenter: parent.verticalCenter; text: sh.label.toUpperCase()
                   color: shm.containsMouse ? T.text : T.text2; font.family: T.font; font.pixelSize: Math.round(10 * g.fz); font.letterSpacing: 1.4 }
        }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: sh.summary
               width: Math.min(implicitWidth, sh.width - 120); elide: Text.ElideLeft; horizontalAlignment: Text.AlignRight
               color: T.muted; font.family: T.font; font.pixelSize: Math.round(11 * g.fz) }
        MouseArea { id: shm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                    onPressed: forceActiveFocus(); onClicked: g.tb.setSection(sh.key, !sh.open) }
    }
    // one card of the lists: thumb, name, set · number, price; the mouse on it shows it big (above everything)
    component CardRow: Item {
        id: cr
        property var c
        property bool newest: false
        width: parent ? parent.width : 0; height: g.rowH
        Rectangle { width: parent.width; height: 1; color: Qt.rgba(1, 1, 1, 0.08) }
        Rectangle { visible: crh.hovered; x: -6; width: parent.width + 8; height: parent.height; radius: 6
                    color: Qt.rgba(1, 1, 1, 0.05) }
        // the mouse on it: big preview (beside the list) and the row's keys (a HoverHandler: it stays on over the
        // keys); a click: edit. The preview only when the mouse really moves – a new card sliding in under a resting
        // mouse shows nothing (Oliver: "the hit still pops up in the middle")
        property bool previewing: false
        HoverHandler {
            id: crh
            onPointChanged: {
                var q = point.scenePosition
                if (!hovered || (q.x === g.lastPt.x && q.y === g.lastPt.y)) return
                g.lastPt = q
                if (!cr.previewing) { cr.previewing = true; g.tb.hoverCard(cr.c.pack, cr.c.idx) }
            }
            onHoveredChanged: if (!hovered && cr.previewing) { cr.previewing = false; g.tb.unhoverCard(cr.c.pack, cr.c.idx) }
        }
        Component.onDestruction: if (previewing) g.tb.unhoverCard(c.pack, c.idx)   // rebuilt list: no preview left behind
        MouseArea {
            anchors.fill: parent; cursorShape: Qt.PointingHandCursor
            onPressed: forceActiveFocus()
            onClicked: g.tb.editCard(cr.c.pack, cr.c.idx)
        }
        Rectangle { visible: cr.newest; x: -T.tile.pad; width: 2; height: parent.height; color: "#ffffff" }   // the newest card
        Thumb { anchors.verticalCenter: parent.verticalCenter; width: T.tile.row * 0.72; height: T.tile.row; src: cr.c.img }
        Column {
            x: T.tile.row * 0.72 + 12; anchors.verticalCenter: parent.verticalCenter
            width: parent.width - x - 64 - (crh.hovered ? crKeys.width + 4 : 0)
            Text { width: parent.width; elide: Text.ElideRight; text: cr.c.name; color: T.text; font.family: T.font; font.pixelSize: Math.round(14 * g.fz) }
            Text { width: parent.width; elide: Text.ElideRight; text: cr.c.sub; color: T.muted; font.family: T.font; font.pixelSize: Math.round(10 * g.fz) }
        }
        // the price always stays far right – the keys appear before it (like the lists' sidebar)
        Text { id: crPrice; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
               text: cr.c.priceShort; color: T.text2; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
        Loader {   // the keys: only while the mouse is on the row (a long list stays light)
            id: crKeys
            active: crh.hovered
            anchors.right: crPrice.left; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter
            sourceComponent: Row {
                spacing: 2
                Btn { height: 26; compact: true; text: cr.c.cond || "NM"; tip: shell.text("Condition – click: next grade")
                      onClicked: g.tb.cardCond(cr.c.pack, cr.c.idx) }
                // the finish as the printing has it; with only one there is nothing to switch
                Btn { height: 26; compact: true; text: cr.c.finish || ""; enabled: (cr.c.finishes || 0) > 1
                      tip: (cr.c.finishes || 0) > 1 ? shell.text("Finish – click: the next one") : shell.text("This print only exists like this")
                      onClicked: g.tb.cardFoil(cr.c.pack, cr.c.idx) }
                Btn { width: 30; height: 26; compact: true; glyph: "pen"; tip: shell.text("Edit card")
                      onClicked: g.tb.editCard(cr.c.pack, cr.c.idx) }
                Btn { width: 30; height: 26; compact: true; glyph: "close"; tip: shell.text("Remove card – Undo in the tile")
                      onClicked: g.tb.removeCard(cr.c.pack, cr.c.idx) }
            }
        }
    }
    // ---- the parts ----
    // ---- the list: every card of this scan, the newest on top. Boosters: per pack – the pack being opened on top
    // and open, older packs folded (a click opens them). A click on a card edits it (condition, finish, language …).
    Component {
        id: listPart
        Column {
            width: parent ? parent.width : 0
            Repeater { model: g.packs ? [] : g.cards
                       CardRow { required property var modelData; required property int index
                                 c: modelData; newest: index === 0 } }
            Text { visible: !g.packs && g.cards.length === 0; height: g.rowH; verticalAlignment: Text.AlignVCenter
                   text: shell.text("Put a card in view"); color: T.dim; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
            Repeater {
                model: g.packs ? g.tb.packs : []
                Column {
                    id: pc
                    required property var modelData
                    width: parent.width
                    readonly property bool cur: modelData.n === (g.s.packNumber || 1)
                    readonly property bool open: g.packOpen[modelData.n] !== undefined ? g.packOpen[modelData.n] : cur
                    Item {   // the pack's head: a click folds it
                        width: parent.width; height: 30
                        Line { anchors.top: parent.top; color: Qt.rgba(1, 1, 1, pc.cur ? 0.24 : 0.09) }
                        Row {
                            anchors.verticalCenter: parent.verticalCenter; spacing: 6
                            Chevron { anchors.verticalCenter: parent.verticalCenter; open: pc.open; size: 12; color: T.muted }
                            Text { anchors.verticalCenter: parent.verticalCenter
                                   text: (shell.text("Pack") + " " + pc.modelData.n).toUpperCase()
                                   color: pc.cur || pkm.containsMouse ? T.text : T.text2; font.family: T.font; font.pixelSize: Math.round(10 * g.fz)
                                   font.letterSpacing: 1.4; font.bold: pc.cur }
                        }
                        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                               text: pc.modelData.cards + " " + shell.text("cards") + " · " + pc.modelData.total
                               color: pc.cur ? T.text2 : T.muted; font.family: T.font; font.pixelSize: Math.round(11 * g.fz) }
                        MouseArea { id: pkm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onPressed: forceActiveFocus()
                                    onClicked: { var o = Object.assign({}, g.packOpen); o[pc.modelData.n] = !pc.open; g.packOpen = o } }
                    }
                    Loader {   // a folded pack builds no rows
                        width: parent.width; active: pc.open; visible: active
                        sourceComponent: Column {
                            width: pc.width
                            Repeater { model: pc.modelData.rows
                                       CardRow { required property var modelData; required property int index
                                                 c: modelData; newest: pc.cur && index === 0 } }
                            Text { visible: pc.modelData.rows.length === 0; height: g.rowH; verticalAlignment: Text.AlignVCenter
                                   text: shell.text("Open the pack – its cards come here")
                                   color: T.dim; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
                            Item {   // + Pack: under the pack being opened
                                visible: pc.cur && g.s.packsShown === true; width: parent.width; height: visible ? 30 : 0
                                Key2 { anchors.verticalCenter: parent.verticalCenter; text: "+ " + shell.text("New pack") + "  N"
                                       onClicked: g.tb.newPack() }
                            }
                        }
                    }
                }
            }
        }
    }
    Component {
        id: setPart
        Column {
            width: parent ? parent.width : 0
            SecHead { key: "set"; label: shell.text("Settings")
                      summary: [g.kinds.filter(function (x) { return x.k === g.s.kind }).map(function (x) { return x.t }).join(""),
                                (g.s.sets || []).map(function (x) { return x.label }).join(" "), g.s.scanLang || ""]
                               .filter(function (x) { return x !== "" }).join(" · ") }
            Column {
                visible: g.secOpen("set"); width: parent.width
                KindSwitch {}
                FieldRow {   // packs: scanned / planned – the number after the slash is the plan
                    visible: g.packs; height: visible ? 32 : 0
                    label: shell.text("Packs")
                    Row {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: 4
                        Text { anchors.verticalCenter: parent.verticalCenter; text: String(g.s.packNumber || 1) + " /"
                               color: T.text; font.family: T.font; font.pixelSize: Math.round(15 * g.fz) }
                        InlineField {
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(40, implicitWidth); height: 24
                            text: g.s.packsPlanned ? String(g.s.packsPlanned) : ""; placeholder: "–"; pixelSize: 15
                            commit: function (v) { return g.tb.setSessionField("packs_planned", v) }
                        }
                    }
                }
                FieldRow {   // boosters: pack type · singles: what it is (a purchase, a trade …)
                    visible: g.s.kind !== "cards"; height: visible ? 32 : 0
                    label: g.packs ? shell.text("Pack type") : shell.text("What")
                    Pick { text: (g.s.packType || shell.text("choose")) + "  ›"; onClicked: g.tb.pickPackType() }
                }
                // the filtered scan (boosters and cards): SCAN° looks in these sets first (recognizer.focus_sets) –
                // whole sets (with Commander, tokens, promos …); ✕ takes one out, ⓘ folds the explanation open
                Item {
                    visible: g.s.kind !== "singles"; width: parent.width; height: visible ? setsCol.height : 0
                    Column {
                        id: setsCol
                        width: parent.width
                        Item {
                            width: parent.width; height: 32
                            Line { anchors.top: parent.top }
                            Row {
                                anchors.verticalCenter: parent.verticalCenter; spacing: 8
                                Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("Only these sets")
                                       color: T.muted; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
                                Rectangle {   // ⓘ: what it does
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 16; height: 16; radius: 8; color: "transparent"
                                    border.width: 1; border.color: g.setInfo || im.containsMouse ? T.text : T.dim
                                    Text { anchors.centerIn: parent; text: "i"; color: g.setInfo || im.containsMouse ? T.text : T.dim
                                           font.family: T.font; font.pixelSize: Math.round(10 * g.fz); font.bold: true }
                                    MouseArea { id: im; anchors.fill: parent; anchors.margins: -5; hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor; onClicked: g.setInfo = !g.setInfo }
                                }
                            }
                            Pick { text: (g.s.sets || []).length ? shell.text("add") + "  ›" : shell.text("none") + "  ›"
                                   onClicked: g.tb.pickSets() }
                        }
                        Flow {   // every chosen set, each with its ✕
                            visible: (g.s.sets || []).length > 0
                            width: parent.width; spacing: 5; bottomPadding: 8
                            Repeater {
                                model: g.s.sets || []
                                Rectangle {
                                    id: chip
                                    required property var modelData
                                    width: chipRow.implicitWidth + 16; height: 22; radius: 6; color: "transparent"
                                    border.width: 1; border.color: Qt.rgba(1, 1, 1, xm.containsMouse ? 0.4 : 0.18)
                                    Row {
                                        id: chipRow
                                        anchors.centerIn: parent; spacing: 6
                                        Text { anchors.verticalCenter: parent.verticalCenter; color: T.text
                                               text: chip.modelData.label + (chip.modelData.n > 1 ? "  +" + (chip.modelData.n - 1) : "")
                                               font.family: T.font; font.pixelSize: Math.round(12 * g.fz) }
                                        Item {   // ✕ (drawn: the font has no such sign)
                                            anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8
                                            Repeater {
                                                model: [45, -45]
                                                Rectangle { required property int modelData
                                                            anchors.centerIn: parent; width: 10; height: 1.4; radius: 0.7
                                                            rotation: modelData; color: xm.containsMouse ? T.top : T.dim }
                                            }
                                        }
                                    }
                                    MouseArea {
                                        id: xm
                                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                        onClicked: g.tb.removeSet(chip.modelData.key)
                                        onContainsMouseChanged: containsMouse
                                            ? shell.tip(chip.modelData.name + (chip.modelData.n > 1 ? " – " + shell.text("with its parts (Commander, tokens, promos …)") : "")
                                                        + " · " + shell.text("click: take out"),
                                                        chip.mapToItem(null, chip.width / 2, chip.height).x, chip.mapToItem(null, 0, chip.height).y)
                                            : shell.tip("", 0, 0)
                                    }
                                }
                            }
                        }
                        Column {   // ⓘ open: what the filtered scan does (pushes the rest down)
                            visible: g.setInfo; width: parent.width; spacing: 4; bottomPadding: 8
                            Text { width: parent.width; wrapMode: Text.WordWrap; color: T.dim; font.family: T.font; font.pixelSize: Math.round(12 * g.fz)
                                   text: shell.text("SCAN° loads your sets in advance and finds their cards faster – often before "
                                                    + "you've fully turned them over. Cards from other sets are still found.") }
                            Text { width: parent.width; wrapMode: Text.WordWrap; color: T.dim; font.family: T.font; font.pixelSize: Math.round(12 * g.fz)
                                   text: shell.text("Your sets then sit ready in memory, so SCAN° doesn't have to load them first. "
                                                    + "Among a few sets there are hardly any look-alike cards, so SCAN° is sure "
                                                    + "sooner and asks less often. If the same card with the same picture is in "
                                                    + "other sets too, it takes the one from your choice. If it reads another set, "
                                                    + "what it reads counts.") }
                        }
                    }
                }
                FieldRow {   // the language of this log: new cards come in it, unclear ones take it (a clear reading wins)
                    label: shell.text("Language")
                    Pick { text: (g.s.scanLang || shell.text("All languages")) + "  ›"; onClicked: g.tb.pickScanLang() }
                }
                FieldRow {   // paid: right in place
                    label: shell.text("Paid")
                    InlineField {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        width: Math.max(90, implicitWidth); height: 24
                        text: g.s.paid || ""; placeholder: shell.text("enter"); align: Text.AlignRight; pixelSize: 15
                        commit: function (v) { return g.tb.setSessionField("paid", v) }
                    }
                }
                Fact { visible: (g.s.balance || "") !== ""; height: visible ? 32 : 0
                       label: shell.text("Balance"); value: g.s.balance || "" }
                FieldRow {
                    label: shell.text("Tags")
                    InlineField {
                        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                        width: Math.min(parent.width, Math.max(90, implicitWidth)); height: 24
                        text: g.s.tags || ""; placeholder: shell.text("none"); align: Text.AlignRight; pixelSize: 14
                        commit: function (v) { return g.tb.setSessionField("tags", v) }
                    }
                }
                InlineArea {   // the free text the stream shows (empty = not shown)
                    height: 56; width: parent.width
                    text: g.s.notes || ""
                    placeholder: shell.text("Text for the stream, e.g. “giveaway at 50 followers” – empty = not shown")
                    commit: function (v) { return g.tb.setSessionField("notes", v) }
                }
            }
        }
    }
    component Scroll: Flickable {
        contentWidth: width; clip: true; boundsBehavior: Flickable.StopAtBounds
        interactive: contentHeight > height
        ScrollHint {}
    }
    ScanTile {
        id: tSession
        key: "session"; title: g.s.scanTitle || "SCAN°"   // "SCAN° – Pokémon" (the brand + the game; the tab stays "Scan")
        ent: g.lay.session; grid: g
        // the preview of a card of the list stands right beside this tile (overlay_paint._beside_list)
        readonly property var place: visible && g.visible ? Qt.rect(x, y, width, height) : Qt.rect(0, 0, 0, 0)
        onPlaceChanged: scanView.setListTile(place.x, place.y, place.width, place.height)
        Component.onCompleted: { scanView.setListTile(place.x, place.y, place.width, place.height)
                                 scanView.setFreeBand(g.freeTop, g.freeBottom) }
        Component.onDestruction: scanView.setListTile(0, 0, 0, 0)
        Connections {   // "where are the log's settings?" -> here: the tile lights up
            target: g.tb
            function onLogPing() { logGlow.restart() }
        }
        Rectangle {
            parent: tSession; anchors.fill: parent; radius: T.tile.radius
            color: "transparent"; border.width: 2; border.color: "#ffffff"; opacity: 0
            SequentialAnimation on opacity {
                id: logGlow; running: false
                NumberAnimation { to: 0.9; duration: 120 }
                NumberAnimation { to: 0; duration: 900; easing.type: Easing.OutCubic }
            }
        }
        // ---- head: the name (right in place; empty = "Scan N"), the value; meta; the sets loading ----
        Column {
            id: sHead
            width: parent.width
            Item {
                width: parent.width; height: 30
                InlineField {
                    width: parent.width - sVal.width - 12; height: 30
                    text: g.s.name || ""; placeholder: g.s.autoName || "Scan"
                    family: T.display; pixelSize: Math.round(24 * g.fz); bold: true; color: T.text
                    commit: function (v) { return g.tb.setSessionField("title", v) }
                }
                Text { id: sVal; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                       text: g.s.value || ""; color: T.top; font.family: T.display; font.pixelSize: Math.round(24 * g.fz); font.weight: Font.DemiBold }
            }
            Text { width: parent.width; height: 21; elide: Text.ElideRight; color: T.muted; font.family: T.font; font.pixelSize: Math.round(12 * g.fz)
                   text: g.s.active === true ? (g.s.meta || "") : shell.text("Starts with the first card") }
            Item {   // the filtered scan loading its sets: what, how far (the app's loading sign, small)
                id: loadRow
                readonly property var ld: g.s.setsLoad || ({})
                visible: (ld.text || "") !== ""
                width: parent.width; height: visible ? 40 : 0
                Item {
                    width: 30; height: 40
                    Loading { small: true; still: true; running: loadRow.visible; scale: 0.5; transformOrigin: Item.TopLeft; y: 2 }
                }
                Column {
                    x: 38; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 38; spacing: 4
                    Item {
                        width: parent.width; height: 16
                        Text { text: loadRow.ld.text || ""; color: T.text2; font.family: T.font; font.pixelSize: Math.round(12 * g.fz)
                               width: parent.width - lc.width - 8; elide: Text.ElideRight }
                        Text { id: lc; anchors.right: parent.right; text: loadRow.ld.count || ""; color: T.muted
                               font.family: T.font; font.pixelSize: Math.round(11 * g.fz) }
                    }
                    Rectangle {
                        width: parent.width; height: 2; radius: 1; color: Qt.rgba(1, 1, 1, 0.1)
                        Rectangle { width: parent.width * (loadRow.ld.frac || 0); height: 2; radius: 1; color: "#ffffff"
                                    Behavior on width { NumberAnimation { duration: 300 } } }
                    }
                }
            }
        }
        // ---- the settings and the list (they scroll) ----
        Scroll {
            id: partS
            y: sHead.height + 4; width: parent.width
            height: foot.y - y - 6
            contentHeight: partC.height
            Column {
                id: partC
                width: partS.width - 12   // the scroll bar runs in the free strip on the right, over nothing
                Loader { width: parent.width; sourceComponent: setPart }
                Loader { width: parent.width; sourceComponent: listPart }
            }
        }
        // ---- the foot: search a card, End scan (the page's most important key); after it: Undo for a moment ----
        Column {
            id: foot
            anchors.bottom: parent.bottom; width: parent.width; spacing: 8
            Item {   // a card taken out with ✕: "„Name“ removed · Undo"
                visible: (g.s.removed || "") !== ""
                width: parent.width; height: visible ? 26 : 0
                Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - undoR.width - 12; elide: Text.ElideRight
                       text: shell.text("“{name}” removed").replace("{name}", g.s.removed || "")
                       color: T.text2; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
                Key2 { id: undoR; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; strong: true
                       text: shell.text("Undo"); onClicked: g.tb.undoRemove() }
            }
            Item {   // after "End scan": "✓ Saved in Logs  Open  Undo", below it "name · 22 cards · 137,18 €" – then it fades
                id: endNote
                readonly property var e: g.s.ended || {}
                readonly property bool on: (e.text || "") !== ""
                property var last: ({})   // what it said – stays while it fades out
                onEChanged: if (on) last = e
                opacity: on ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 700; easing.type: Easing.InOutQuad } }
                visible: opacity > 0.01
                width: parent.width; height: visible ? ((endNote.last.detail || "") !== "" ? 44 : 26) : 0
                Text { y: 4; width: parent.width - endKeys.width - 12; elide: Text.ElideRight
                       text: (endNote.last.id ? "✓ " : "") + (endNote.last.text || "")
                       color: T.text; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
                Text { y: 24; width: parent.width; elide: Text.ElideRight; visible: text !== ""
                       text: endNote.last.detail || ""
                       color: T.text2; font.family: T.font; font.pixelSize: Math.round(12 * g.fz) }
                Row {
                    id: endKeys
                    anchors.right: parent.right; y: 4
                    spacing: 14
                    Key2 { visible: !!endNote.last.id; strong: true; enabled: endNote.on
                           text: shell.text("Open"); onClicked: g.tb.openEnded() }
                    Key2 { id: undoK; visible: !!endNote.last.undo; strong: true; enabled: endNote.on
                           text: shell.text("Undo"); onClicked: g.tb.undoEnd() }
                }
            }
            Rectangle {   // the card search: typing opens the search window with what was typed
                width: parent.width; height: 34; radius: 8
                // its own dark ground: readable on the frosted glass, also over a bright camera image
                color: Qt.rgba(0.02, 0.02, 0.025, sfm.containsMouse || sIn.activeFocus ? 0.7 : 0.55)
                border.width: 1; border.color: Qt.rgba(1, 1, 1, sIn.activeFocus ? 0.5 : 0.26)
                NavIcon { x: 9; anchors.verticalCenter: parent.verticalCenter; key: "search"; s: 0.7; color: T.muted
                          play: sfm.containsMouse }
                Text { x: 32; anchors.verticalCenter: parent.verticalCenter; visible: sIn.text === ""
                       text: shell.text("Search card …"); color: T.text2; font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
                Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                       text: "K"; color: T.muted; font.family: T.font; font.pixelSize: Math.round(11 * g.fz) }
                TextInput {
                    id: sIn
                    x: 32; width: parent.width - 60; anchors.verticalCenter: parent.verticalCenter
                    color: T.text; font.family: T.font; font.pixelSize: Math.round(13 * g.fz); clip: true
                    onTextEdited: if (text !== "") { var t = text; text = ""; focus = false; g.tb.searchCard(t) }
                    Keys.onReturnPressed: g.tb.searchCard("")
                }
                MouseArea { id: sfm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.IBeamCursor
                            onClicked: g.tb.searchCard("") }
            }
            Rectangle {   // End scan: the biggest, brightest key of the page
                id: endK
                readonly property bool can: g.s.active === true || (g.s.cards || 0) > 0
                width: parent.width; height: 46; radius: 10
                color: !can ? Qt.rgba(1, 1, 1, 0.08) : em.pressed ? "#d6d6d6" : em.containsMouse ? "#ffffff" : "#ececec"
                Behavior on color { ColorAnimation { duration: 120 } }
                Row {
                    anchors.centerIn: parent; spacing: 10
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 11; height: 11; radius: 2
                                color: endK.can ? "#000000" : T.dim }
                    Text { anchors.verticalCenter: parent.verticalCenter; text: shell.text("End scan")
                           color: endK.can ? "#000000" : T.dim; font.family: T.font; font.pixelSize: Math.round(16 * g.fz); font.bold: true }
                }
                MouseArea {
                    id: em
                    anchors.fill: parent; hoverEnabled: true; enabled: endK.can; cursorShape: Qt.PointingHandCursor
                    onPressed: forceActiveFocus()
                    onClicked: g.tb.endSession()
                    onContainsMouseChanged: containsMouse
                        ? shell.tip(shell.text("Ends the log right away – the cards go into your library as set in Settings"),
                                    endK.mapToItem(null, endK.width / 2, 0).x, endK.mapToItem(null, 0, 0).y - 34)
                        : shell.tip("", 0, 0)
                }
            }
        }
    }

    // ================= Last hit · Biggest hit =================
    component HitTile: ScanTile {
        id: ht
        tight: true                        // a narrow edge: the card fills the tile
        property var h: ({})
        // the large form's type follows the tile's width (the card is the tile – the words go with it)
        readonly property real nameSize: Math.max(18, Math.min(30, width * 0.068))
        readonly property real priceSize: Math.max(30, Math.min(58, width * 0.125))
        readonly property real textH: nameSize * 1.3 + 16 + priceSize * 1.15
        property bool jump: false          // "Last hit": every new card jumps in (the hit look – card, name, price)
        readonly property string size: g.sizeOf(ht, g.hd + g.hitTextH + 150)
        readonly property bool has: (h.name || "") !== ""
        // small, only what helps at a glance: the set, and the finish only when it is foil (editing: the scan list)
        readonly property string small: [(h.setName || h.set || ""), h.fancy || ""].filter(function (x) { return x !== "" }).join(" · ")
        // a new card: the tile flashes (a hit – from "Hit from" in Settings – a bit longer and brighter); "Last hit":
        // the card jumps in – a new Biggest Hit higher and with more glow. ONE sequence per tile, started once the new
        // picture is decoded (not while it loads), at the latest after 450 ms
        property string seen: ""
        property bool pending: false
        onHChanged: {
            var k = h.key || ""
            if (k !== "" && seen !== "" && k !== seen) {
                pending = true
                if (jump) bigText.opacity = 0   // name and price come with the jump
                waitImg.restart()
                Qt.callLater(function () { if (bigImg.settled) ht.play() })   // the same picture: no waiting
            }
            seen = k
        }
        function play() {
            if (!pending) return
            pending = false
            waitImg.stop()
            jumpIn.stop(); jumpTop.stop(); flash.stop()
            flash.restart()
            if (jump) (h.isTop ? jumpTop : jumpIn).restart()
            else bigText.opacity = 1
        }
        Timer { id: waitImg; interval: 450; onTriggered: ht.play() }
        Rectangle {
            id: glow
            parent: ht; anchors.fill: parent; radius: T.tile.radius
            color: "#ffffff"; opacity: 0
            border.width: 2; border.color: "#ffffff"
        }
        SequentialAnimation {   // (on a plain rectangle – no layer, no effect)
            id: flash
            OpacityAnimator { target: glow; to: ht.h.isHit || (ht.h.isTop && ht.jump) ? 0.3 : 0.16; duration: 90 }
            OpacityAnimator { target: glow; to: 0; duration: ht.h.isTop && ht.jump ? 2000 : ht.h.isHit ? 1400 : 700
                              easing.type: Easing.OutCubic }
        }
        // the jump: the card comes in small and tilted and lands with a little overshoot, name and price follow
        // (Animators only – on the render thread, no stutter while the camera runs)
        ParallelAnimation {
            id: jumpIn
            ScaleAnimator { target: bigImg; from: 0.55; to: 1; duration: 520; easing.type: Easing.OutBack; easing.overshoot: 2.2 }
            RotationAnimator { target: bigImg; from: -9; to: 0; duration: 520; easing.type: Easing.OutBack }
            SequentialAnimation {
                PauseAnimation { duration: 120 }
                ParallelAnimation {
                    OpacityAnimator { target: bigText; from: 0; to: 1; duration: 320 }
                    YAnimator { target: bigText; from: 14; to: 0; duration: 380; easing.type: Easing.OutCubic }
                }
            }
        }
        // a new Biggest Hit: the same jump, from further away, higher and with a little turn back
        ParallelAnimation {
            id: jumpTop
            SequentialAnimation {
                ScaleAnimator { target: bigImg; from: 0.35; to: 1.08; duration: 560; easing.type: Easing.OutCubic }
                ScaleAnimator { target: bigImg; from: 1.08; to: 1; duration: 380; easing.type: Easing.InOutQuad }
            }
            SequentialAnimation {
                RotationAnimator { target: bigImg; from: -16; to: 4; duration: 560; easing.type: Easing.OutCubic }
                RotationAnimator { target: bigImg; from: 4; to: 0; duration: 380; easing.type: Easing.InOutQuad }
            }
            SequentialAnimation {
                PauseAnimation { duration: 260 }
                ParallelAnimation {
                    OpacityAnimator { target: bigText; from: 0; to: 1; duration: 380 }
                    YAnimator { target: bigText; from: 20; to: 0; duration: 460; easing.type: Easing.OutCubic }
                }
            }
        }
        Text { visible: !ht.has; anchors.centerIn: parent; text: shell.text("Nothing scanned yet"); color: T.dim
               font.family: T.font; font.pixelSize: Math.round(13 * g.fz) }
        Row {   // one row
            visible: ht.has && ht.size === "S"
            anchors.fill: parent; spacing: 10
            Thumb { width: 26; height: 36; anchors.verticalCenter: parent.verticalCenter; src: ht.h.img || ""
                    onShown: ht.play() }
            Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - 26 - prS.width - 24; elide: Text.ElideRight
                   text: ht.h.name || ""; color: T.text; font.family: T.font; font.pixelSize: Math.round(14 * g.fz); font.bold: true }
            Text { id: prS; anchors.verticalCenter: parent.verticalCenter; text: ht.h.price || ""; color: T.top
                   font.family: T.display; font.pixelSize: Math.round(20 * g.fz); font.weight: Font.DemiBold }
        }
        Row {   // medium
            visible: ht.has && ht.size === "M"
            anchors.verticalCenter: parent.verticalCenter; width: parent.width; spacing: 12
            Thumb { width: 52; height: 72; src: ht.h.img || ""; onShown: ht.play() }
            Column {
                width: parent.width - 52 - 12; anchors.verticalCenter: parent.verticalCenter; spacing: 2
                Text { width: parent.width; elide: Text.ElideRight; text: ht.h.name || ""; color: T.text
                       font.family: T.display; font.pixelSize: Math.round(18 * g.fz); font.weight: Font.Bold }
                Text { text: ht.h.price || ""; color: T.top; font.family: T.display; font.pixelSize: Math.round(28 * g.fz); font.weight: Font.Bold }
            }
        }
        Item {   // large: the card on top (as big as fits), below it the name bold, the set small, the price big
            visible: ht.has && ht.size === "L"
            width: parent.width; height: parent.height
            Thumb { id: bigImg; res: 600
                    anchors.horizontalCenter: parent.horizontalCenter
                    height: Math.min(parent.height - ht.textH, parent.width / 0.716); width: height * 0.716
                    src: ht.h.img || ""; onShown: ht.play() }
            Item {
                y: bigImg.height + 6; width: parent.width; height: ht.textH - 6
            Column {
                id: bigText   // (its y only for the jump: from a little lower to 0)
                width: parent.width; spacing: 0
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                       text: ht.h.name || ""; color: T.text
                       font.family: T.display; font.pixelSize: ht.nameSize; font.weight: Font.Bold }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                       visible: ht.small !== ""; text: ht.small; color: T.muted; font.family: T.font; font.pixelSize: Math.round(11 * g.fz) }
                Text { width: parent.width; horizontalAlignment: Text.AlignHCenter
                       fontSizeMode: Text.HorizontalFit; minimumPixelSize: 22
                       text: ht.h.price || ""; color: T.top; font.family: T.display; font.pixelSize: ht.priceSize; font.weight: Font.Bold }
            }
            }
        }
    }
    HitTile {
        id: tHit; key: "hit"; title: shell.text("Last hit"); ent: g.lay.hit; grid: g; h: g.tb.hit; jump: true
    }
    HitTile { id: tTop; key: "top"; title: shell.text("Biggest hit"); ent: g.lay.top; grid: g; h: g.tb.top }

    // ================= Status: the recognition's chain =================
    // the real steps of SCAN° in order (qscan.STEP_OF) – done ones lit, the current one pulsing, the rest dim; under it
    // a segmented line with a light running along the part reached. Taller: what it is doing and the card. Animators
    // only (render thread). No invented steps: without a card in the frame it says so instead.
    ScanTile {
        id: tStatus
        key: "status"; title: g.s.scanTitle || shell.text("Status")   // "SCAN° – Pokémon", like the scan tile
        ent: g.lay.status; grid: g
        readonly property int step: g.stage.step === undefined ? -1 : g.stage.step
        readonly property var steps: [shell.text("Frame"), shell.text("Fingerprint"), shell.text("Image match"),
                                      shell.text("Print"), shell.text("Price")]
        // too narrow for a word: ALL columns shorten alike (long → short → only lamp and segment), never one word
        // shrunk on its own
        readonly property var stepsShort: [shell.text("Frame"), shell.text("Fingerpr."), shell.text("Match"),
                                           shell.text("Print"), shell.text("Price")]
        readonly property real colW: (chainW - 12) / 5 - 12
        // measured with FontMetrics (a function, no text property written in the binding – no binding loop)
        function widest(list) { var w = 0; for (var i = 0; i < list.length; i++)
                                    w = Math.max(w, stepM.advanceWidth(list[i].toUpperCase()) + 1.2 * list[i].length)
                                return w }
        FontMetrics { id: stepM; font.family: T.display; font.weight: Font.DemiBold; font.pixelSize: Math.round(11.5 * g.fz) }
        readonly property int labelMode: colW >= widest(steps) ? 0 : colW >= widest(stepsShort) ? 1 : 2
        // a card lies there without a hit: instead of the chain, the offer to search (key K) – nothing opens by itself
        readonly property bool offer: g.stage.offer === true
        // the scanner asks in the card search ("print" / "lang"), or waits for it to be free ("…_wait": key K)
        readonly property string question: g.stage.question || ""
        readonly property bool note: offer || question !== ""
        // the chain keeps running beside a note (an offer, not a stop – Oliver): chain on the left, note on the right
        readonly property bool chain: step >= 0
        readonly property real chainW: note && chain ? Math.round(width * 0.55) : width
        readonly property string price: step >= 4 ? (g.tb.hit.price || "") : ""
        Column {
            width: parent.width
            anchors.verticalCenter: tStatus.compact ? parent.verticalCenter : undefined
            spacing: 6
            Item {   // the chain (or, without a card, what to do)
                width: parent.width; height: 20
                Row {   // one column per step, exactly over its segment of the line below (same widths and gaps)
                    visible: tStatus.chain
                    anchors.verticalCenter: parent.verticalCenter
                    width: tStatus.chainW
                    spacing: 3
                    Repeater {
                        model: tStatus.steps
                        Row {
                            id: stp
                            required property string modelData
                            required property int index
                            readonly property bool done: index < tStatus.step || tStatus.step >= 4
                            readonly property bool now: index === tStatus.step && tStatus.step < 4
                            width: (parent.width - 12) / 5; clip: true
                            spacing: 5
                            Item {   // the step's lamp: lit when done, pulsing while it runs, an outline before
                                anchors.verticalCenter: parent.verticalCenter
                                width: 7; height: 7
                                Rectangle {
                                    visible: !stp.now
                                    anchors.fill: parent; radius: 1.5
                                    color: stp.done ? "#ffffff" : "transparent"
                                    border.width: 1; border.color: stp.done ? "#ffffff" : T.dim
                                }
                                Rectangle {
                                    id: pulse
                                    visible: stp.now
                                    anchors.fill: parent; radius: 1.5; color: "#ffffff"
                                    SequentialAnimation {
                                        running: stp.now; loops: Animation.Infinite
                                        OpacityAnimator { target: pulse; from: 1; to: 0.2; duration: 420; easing.type: Easing.InOutSine }
                                        OpacityAnimator { target: pulse; from: 0.2; to: 1; duration: 420; easing.type: Easing.InOutSine }
                                    }
                                }
                            }
                            Text {   // too long for its column: tighter letters first, then a smaller size – never wider
                                id: stpT
                                anchors.verticalCenter: parent.verticalCenter
                                width: stp.width - 12; height: 20; verticalAlignment: Text.AlignVCenter
                                visible: tStatus.labelMode < 2
                                text: (index === 4 && tStatus.price !== "" ? tStatus.price
                                       : tStatus.labelMode === 1 ? tStatus.stepsShort[index] : stp.modelData).toUpperCase()
                                color: stp.now ? T.top : stp.done ? T.text2 : T.dim
                                font.family: T.display; font.pixelSize: Math.round(11.5 * g.fz); font.weight: Font.DemiBold
                                font.letterSpacing: 1.2; elide: Text.ElideRight
                            }
                        }
                    }
                }
                Row {   // "Search is taking long – search? [K]" / "Card found – which version?" / "Pick the language"
                    visible: tStatus.note
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: tStatus.chain ? parent.right : undefined
                    spacing: 10
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        width: (tStatus.chain ? parent.parent.width - tStatus.chainW - 16 : tStatus.width) - 40
                        horizontalAlignment: tStatus.chain ? Text.AlignRight : Text.AlignLeft
                        elide: Text.ElideRight
                        // beside the chain in a narrow tile: the short form instead of a cut-off sentence
                        readonly property string longText: (tStatus.offer ? shell.text("Search is taking long – search?")
                               : tStatus.question.indexOf("print") === 0 ? shell.text("Card found – which version?")
                               : shell.text("Pick the language")).toUpperCase()
                        readonly property string shortText: (tStatus.offer ? shell.text("Search?")
                               : tStatus.question.indexOf("print") === 0 ? shell.text("Which version?")
                               : shell.text("Language?")).toUpperCase()
                        Text {   // the long sentence laid out at this width, unseen: does it fit without "…"?
                            id: noteProbe; visible: false; width: parent.width; elide: Text.ElideRight
                            text: parent.longText; font: parent.font
                        }
                        text: noteProbe.truncated && tStatus.chain ? shortText : longText
                        color: T.top; font.family: T.display; font.pixelSize: Math.round(11.5 * g.fz)
                        font.weight: Font.DemiBold; font.letterSpacing: 1.2
                    }
                    Rectangle {   // the key cap K (not while the question is open in the card search)
                        visible: tStatus.offer || tStatus.question.indexOf("_wait") > 0
                        anchors.verticalCenter: parent.verticalCenter
                        width: 22; height: 20; radius: 4
                        color: offerMa.containsMouse ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.06)
                        border.width: 1; border.color: Qt.rgba(1, 1, 1, offerMa.containsMouse ? 0.7 : 0.45)
                        Text { anchors.centerIn: parent; text: "K"; color: T.top; font.family: T.font
                               font.pixelSize: Math.round(12 * g.fz); font.bold: true }
                        MouseArea { id: offerMa; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor; onClicked: scanView.key("K") }
                    }
                }
                Text {
                    visible: !tStatus.chain && !tStatus.note
                    anchors.verticalCenter: parent.verticalCenter; width: parent.width; elide: Text.ElideRight
                    text: (g.stage.text || shell.text("Put a card in view")).toUpperCase()
                    color: T.text2; font.family: T.display; font.pixelSize: Math.round(12 * g.fz); font.weight: Font.DemiBold
                    font.letterSpacing: 1.6
                }
            }
            Item {   // the segmented line: as far as the chain has come, a light running along it
                width: tStatus.chainW; height: 3
                visible: tStatus.chain
                Row {
                    anchors.fill: parent; spacing: 3
                    Repeater {
                        model: 5
                        Rectangle {
                            required property int index
                            width: (parent.width - 12) / 5; height: 3; radius: 1
                            color: index <= tStatus.step ? Qt.rgba(1, 1, 1, index === tStatus.step && tStatus.step < 4 ? 0.55 : 0.85)
                                                         : Qt.rgba(1, 1, 1, 0.12)
                        }
                    }
                }
                Rectangle {   // the running light (only while it is working)
                    id: runner
                    width: 26; height: 3; radius: 1.5
                    visible: tStatus.step >= 0 && tStatus.step < 4
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
                        GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 1) }
                        GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) }
                    }
                    XAnimator on x {
                        running: runner.visible; loops: Animation.Infinite
                        from: -26; to: (parent.width - 12) / 5 * (tStatus.step + 1) + 3 * tStatus.step
                        duration: 900
                    }
                }
            }
            Text {   // taller: what it is doing, and the card it is on
                visible: !tStatus.compact && tStatus.chain
                width: parent.width; elide: Text.ElideRight
                text: [g.stage.text || "", g.stage.card || ""].filter(function (x) { return x !== "" }).join("  ·  ")
                color: T.muted; font.family: T.font; font.pixelSize: Math.round(11 * g.fz)
            }
        }
    }

    // ================= Stats (of this log / total) – only when picked in the tile drawer =================
    ScanTile {
        id: tStats
        key: "stats"; title: shell.text("Stats")
        ent: g.lay.stats; grid: g
        // the charts are built only while the tile is shown (qscan.setStatsTile); wide: two charts side by side
        readonly property bool live: visible && g.visible
        readonly property bool wide: width >= 620
        function report() { scanView.setStatsTile(live, wide) }
        onLiveChanged: report()
        onWideChanged: report()
        Component.onCompleted: report()
        Component.onDestruction: scanView.setStatsTile(false, false)
        Flickable {
            id: statsF
            anchors.fill: parent
            visible: tStats.live
            contentWidth: width; contentHeight: statsM.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            ScrollHint {}
            Mirror { id: statsM; width: statsF.width; mirror: scanView.statsTileForm
                     onHeightChanged: g.statsH = height }
        }
    }
}
