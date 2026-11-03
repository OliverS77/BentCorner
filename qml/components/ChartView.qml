// Charts native in Qt Quick (data: qcharts.py). Kinds: frame (tile with title, toggle and content:
// vbars · line · donut · hbars · empty), kpis, hero, section, panel (small stream charts: tiles · list · …).
// When the data changes the contents build up (t 0→1); hover shows a label, click reports acted(["pick", i]),
// the toggle acted(["mode", i]).
import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property var spec: ({})
    signal acted(var value)
    // s = last shown data: only rebuild on a real difference (otherwise the bars would rebuild on every refresh)
    property var s: ({})
    property string _last: ""
    readonly property string kind: s && s.kind ? s.kind : ""
    implicitHeight: s && s.h ? s.h : 200

    property real t: 1
    onSpecChanged: {
        var j = JSON.stringify(spec || {})
        if (j === _last) return
        _last = j; s = spec
        t = 0; build.stop(); waiting = true
    }
    // The build-up starts with the first frame that shows the chart: a page full of charts takes a moment to make
    // (a tab of the stats ~0.35 s) – started right away, that much of the 0.9 s was gone before anything showed and
    // the curve jumped instead of drawing itself.
    property bool waiting: false
    Connections {
        target: root.Window.window
        enabled: root.waiting
        function onFrameSwapped() { root.waiting = false; build.restart() }
    }
    NumberAnimation { id: build; target: root; property: "t"; from: 0; to: 1; duration: 900 * (shell && shell.animate ? Math.max(0.01, shell.speed) : 0.01); easing.type: Easing.OutCubic }
    function ease(u) { u = Math.max(0, Math.min(1, u)); return 1 - Math.pow(1 - u, 3) }

    // ---------- Label on hover ----------
    property var tipLines: []
    property point tipAt: Qt.point(0, 0)
    function showTip(lines, x, y) { tipLines = lines || []; tipAt = Qt.point(x, y) }
    function hideTip() { tipLines = [] }

    Loader {
        anchors.fill: parent
        sourceComponent: root.kind === "kpis" ? cKpis : root.kind === "hero" ? cHero : root.kind === "section" ? cSection
                       : root.kind === "frame" ? cFrame : root.kind === "panel" ? cPanel : null
    }
    Rectangle {
        id: tip
        z: 50
        visible: root.tipLines.length > 0
        width: tipCol.implicitWidth + 20; height: tipCol.implicitHeight + 14
        x: Math.min(root.tipAt.x + 14, root.width - width - 6)
        y: Math.max(6, root.tipAt.y - height - 8)
        radius: 8
        color: Qt.rgba(0.08, 0.08, 0.09, 0.96); border.width: 1; border.color: T.line2
        Column {
            id: tipCol
            x: 10; y: 7
            Repeater { model: root.tipLines
                Text { required property var modelData; text: modelData; color: T.text; font.family: T.font; font.pixelSize: 12 } }
        }
    }

    // ================= KPI tiles =================
    Component {
        id: cKpis
        Row {
            spacing: 12
            readonly property var items: root.s.items || []
            readonly property real tw: (root.width - 12 * Math.max(0, items.length - 1)) / Math.max(1, items.length)
            Repeater {
                model: parent.items
                delegate: Rectangle {
                    required property var modelData
                    width: parent.tw; height: root.height - 2
                    radius: Math.min(14, T.panelRadius)
                    gradient: Gradient { GradientStop { position: 0; color: Qt.lighter(T.surface, 1.06) }
                                         GradientStop { position: 1; color: Qt.darker(T.surface, 1.12) } }
                    border.width: 1; border.color: modelData.first ? modelData.color : T.line
                    opacity: 0.3 + 0.7 * root.t
                    Text { x: 16; y: 10; width: parent.width - 28; elide: Text.ElideRight; text: modelData.title
                           color: T.muted; font.family: T.font; font.pixelSize: 12 }
                    Text { x: 16; y: 28; width: parent.width - 28; elide: Text.ElideRight; text: modelData.text
                           color: modelData.color; font.family: T.display; font.pixelSize: 26 }
                    Text { x: 16; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; width: parent.width - 28
                           elide: Text.ElideRight; text: modelData.extra; color: T.dim; font.family: T.font; font.pixelSize: 11 }
                }
            }
        }
    }

    // ================= Balance header =================
    Component {
        id: cHero
        Rectangle {
            radius: 16
            color: Qt.darker(T.surface, 1.05); border.width: 1; border.color: T.line
            Column {
                id: hl
                x: 26; y: 20; width: (parent.width - 52) * 0.6 - 30
                spacing: 4
                Text { text: root.s.kicker || ""; color: T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true; font.letterSpacing: 2 }
                Text { text: root.s.number || ""; color: root.s.color || T.text; font.family: T.display; font.pixelSize: 64
                       opacity: root.t; transform: Translate { y: (1 - root.t) * 10 } }
                Text { width: parent.width; wrapMode: Text.Wrap; textFormat: Text.RichText; text: root.s.sentence || ""
                       color: T.text2; font.family: T.font; font.pixelSize: 15 }
            }
            Rectangle { x: hl.x + hl.width + 30; y: 20; width: 1; height: parent.height - 40; color: T.line }
            Column {
                x: hl.x + hl.width + 61; width: parent.width - x - 26
                anchors.verticalCenter: parent.verticalCenter
                spacing: 12
                Repeater {
                    model: root.s.facts || []
                    Item {
                        required property var modelData
                        width: parent.width; height: 24
                        Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.label; color: T.dim
                               font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1 }
                        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: modelData.value
                               textFormat: Text.RichText; color: T.text; font.family: T.font; font.pixelSize: 16; font.bold: true }
                    }
                }
            }
        }
    }

    // ================= Section header =================
    Component {
        id: cSection
        Item {
            Text { id: sn; y: 4; text: root.s.number || ""; color: T.dim; font.family: T.display; font.pixelSize: 15 }
            Text { id: sq; x: sn.width + 16; y: 0; text: root.s.question || ""; color: T.text; font.family: T.display; font.pixelSize: 20 }
            Rectangle { x: sq.x + sq.width + 16; y: 15; width: Math.max(0, root.width - x - 2); height: 1; color: T.line }
            Text { x: sq.x; y: 30; visible: !!root.s.note; text: root.s.note || ""; color: T.muted; font.family: T.font; font.pixelSize: 13 }
        }
    }

    // ================= Tile with title =================
    Component {
        id: cFrame
        Rectangle {
            id: fr
            radius: Math.min(16, T.panelRadius)
            gradient: Gradient { GradientStop { position: 0; color: Qt.lighter(T.surface, 1.05) }
                                 GradientStop { position: 1; color: Qt.darker(T.surface, 1.1) } }
            border.width: 1; border.color: T.line
            Text { id: ft; x: 18; y: 13; text: root.s.title || ""; color: T.text; font.family: T.font; font.pixelSize: 16; font.bold: true }
            Btn {   // optional button right next to the title (e.g. „More statistics →“) – reports acted(["link"])
                id: flink
                visible: !!root.s.link
                x: ft.x + ft.implicitWidth + 12; y: 8; height: 28; compact: true; width: implicitWidth
                text: root.s.link || ""
                onClicked: root.acted(["link"])
            }
            Text { visible: !(root.s.modes && root.s.modes.length); anchors.right: parent.right; anchors.rightMargin: 18 + (root.s.subPad || 0); y: 15
                   width: Math.max(0, parent.width - ft.width - 56 - (flink.visible ? flink.width + 12 : 0) - (root.s.subPad || 0))
                   horizontalAlignment: Text.AlignRight; elide: Text.ElideRight
                   text: root.s.sub || ""; color: T.dim; font.family: T.font; font.pixelSize: 12 }
            Rectangle {   // toggle
                visible: !!(root.s.modes && root.s.modes.length)
                anchors.right: parent.right; anchors.rightMargin: 16; y: 11
                height: 28; radius: 14; width: modeRow.width + 6
                color: Qt.darker(T.surface, 1.3); border.width: 1; border.color: T.line
                Row {
                    id: modeRow
                    x: 3; y: 3
                    Repeater {
                        model: root.s.modes || []
                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            height: 22; radius: 11; width: mt.implicitWidth + 22
                            color: index === root.s.mode ? T.surface2 : (mh.hovered ? Qt.lighter(T.surface, 1.15) : "transparent")
                            Text { id: mt; anchors.centerIn: parent; text: modelData; color: index === root.s.mode ? T.text : T.muted
                                   font.family: T.font; font.pixelSize: 12; font.bold: true }
                            HoverHandler { id: mh; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: root.acted(["mode", index]) }
                        }
                    }
                }
            }
            Loader {
                id: body
                x: 18; y: 52; width: fr.width - 36; height: fr.height - 68
                readonly property var b: root.s.body || ({})
                sourceComponent: b.type === "vbars" ? cVBars : b.type === "line" ? cLine : b.type === "donut" ? cDonut
                               : b.type === "hbars" ? cHBars : b.type === "empty" ? cEmpty : null
            }
        }
    }
    // ================= Small stream chart =================
    Component {
        id: cPanel
        Rectangle {
            id: pn
            radius: 12
            color: Qt.lighter(T.surface, 1.1)
            Text { id: ptitle; x: 14; y: 10; visible: !!root.s.title; text: root.s.title || ""; color: T.muted
                   font.family: T.font; font.pixelSize: 15; font.bold: true }
            Loader {
                x: 14; y: root.s.title ? 38 : 10; width: pn.width - 28; height: pn.height - y - 10
                readonly property var b: root.s.body || ({})
                sourceComponent: b.type === "vbars" ? cVBars : b.type === "line" ? cLine : b.type === "donut" ? cDonut
                               : b.type === "tiles" ? cTiles : b.type === "list" ? cList : b.type === "empty" ? cEmpty : null
            }
        }
    }

    Component {
        id: cEmpty
        Text { horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap
               text: parent.b.text || ""; color: T.dim; font.family: T.font; font.pixelSize: 14 }
    }

    // ---------- vertical bars (sessions, packs, histogram, mana curve, stream) ----------
    Component {
        id: cVBars
        Item {
            id: vb
            readonly property var b: parent.b
            readonly property bool hasGrid: !!(b.grid && b.grid.length)
            readonly property bool hasValues: { var bs = b.bars || []; for (var i = 0; i < bs.length; i++) if (bs[i].value) return true; return false }
            readonly property var pairs: b.pairs || []
            readonly property int n: pairs.length ? pairs.length : (b.bars || []).length
            readonly property real lx: hasGrid ? 66 : 4
            readonly property real ty: (hasValues ? 18 : 6) + (b.legend && b.legend.length ? 16 : 0)
            readonly property real pw: width - lx - 4
            readonly property real ph: height - ty - 22
            readonly property real slot: pw / Math.max(1, n)
            readonly property real bw: Math.min(b.maxw || 46, slot * (b.thin ? 0.86 : 0.62))
            function yOf(v) { return ty + ph - ph * v / Math.max(1e-9, b.vmax) }
            function local(i) { return root.ease(root.t * 1.4 - i / Math.max(1, n) * 0.4) }
            property int hover: -1
            // grid
            Repeater {
                model: vb.hasGrid ? b.grid : []
                Item {
                    required property var modelData
                    required property int index
                    readonly property real gy: vb.ty + vb.ph - vb.ph * index / 4
                    Rectangle { x: vb.lx; y: parent.gy; width: vb.pw; height: 1; color: index ? Qt.rgba(1, 1, 1, 0.05) : T.line }
                    Text { x: vb.lx - 64; y: parent.gy - 8; width: 58; horizontalAlignment: Text.AlignRight; text: modelData
                           color: T.dim; font.family: T.font; font.pixelSize: 11 }
                }
            }
            Rectangle { visible: !vb.hasGrid; x: vb.lx; y: vb.ty + vb.ph; width: vb.pw; height: 1; color: T.line }
            // legend
            Row {
                visible: !!(b.legend && b.legend.length)
                anchors.right: parent.right; y: 0; spacing: 14
                Repeater { model: b.legend || []
                    Row { required property var modelData; spacing: 6
                          Rectangle { width: 10; height: 10; radius: 2; color: modelData.color; anchors.verticalCenter: parent.verticalCenter }
                          Text { text: modelData.text; color: T.muted; font.family: T.font; font.pixelSize: 12 } } }
            }
            // bars
            Repeater {
                model: b.bars || []
                Item {
                    required property var modelData
                    required property int index
                    readonly property real lv: vb.local(index)
                    readonly property real h: vb.ph * modelData.v / Math.max(1e-9, b.vmax) * lv
                    x: vb.lx + vb.slot * index + (vb.slot - vb.bw) / 2
                    width: vb.bw; height: vb.ty + vb.ph
                    Rectangle {
                        y: vb.ty + vb.ph - parent.h; width: parent.width; height: Math.max(0, parent.h)
                        radius: Math.min(6, width / 3)
                        gradient: Gradient { GradientStop { position: 0; color: modelData.color }
                                             GradientStop { position: 1; color: b.bottom || Qt.darker(modelData.color, 2.5) } }
                        border.width: vb.hover === index ? 1.5 : 0; border.color: T.text
                    }
                    Rectangle {   // inner bars (mana curve: creatures)
                        visible: !!b.inner && (modelData.inner || 0) > 0
                        readonly property real ih: vb.ph * (modelData.inner || 0) / Math.max(1e-9, b.vmax) * parent.lv
                        y: vb.ty + vb.ph - ih; width: parent.width; height: ih; radius: 5; color: b.inner || "transparent"
                    }
                    Text { visible: !!modelData.value; width: parent.width + 16; x: -8; horizontalAlignment: Text.AlignHCenter
                           y: vb.ty + vb.ph - parent.h - 17; text: modelData.value || ""; color: T.text; font.family: T.font; font.pixelSize: 11 }
                    Text { visible: !!modelData.label; width: vb.slot + 30; x: (parent.width - width) / 2; horizontalAlignment: Text.AlignHCenter
                           y: vb.ty + vb.ph + 4; text: modelData.label || ""; color: T.dim; font.family: T.font; font.pixelSize: 11 }
                }
            }
            // pairs (value/spending)
            Repeater {
                model: vb.pairs
                Item {
                    required property var modelData
                    required property int index
                    x: vb.lx + vb.slot * index; width: vb.slot; height: vb.ty + vb.ph
                    Repeater {
                        model: [modelData.a, modelData.b]
                        Rectangle {
                            required property var modelData
                            required property int index
                            readonly property real h: vb.ph * modelData / Math.max(1e-9, b.vmax) * root.t
                            x: vb.slot * (0.14 + 0.37 * index); width: vb.slot * 0.33
                            y: vb.ty + vb.ph - h; height: Math.max(0, h); radius: 3
                            color: (b.colors || ["#cccccc", "#ff6b6b"])[index]
                        }
                    }
                    Text { width: parent.width; horizontalAlignment: Text.AlignHCenter; y: vb.ty + vb.ph + 4; text: modelData.label || ""
                           color: T.dim; font.family: T.font; font.pixelSize: 11 }
                }
            }
            // line over the bars (stake) + horizontal (average, spending)
            Shape {
                anchors.fill: parent
                visible: !!b.line
                layer.enabled: true; layer.samples: 4   // smoothed; the curve renderer ignores clipping (scroll areas)
                ShapePath {
                    strokeColor: b.line ? b.line.color : "transparent"; strokeWidth: 2; fillColor: "transparent"
                    PathPolyline {
                        path: {
                            var out = [], vals = b.line ? b.line.vals : [], bs = b.bars || []
                            for (var i = 0; i < vals.length; i++) if (vals[i] !== null && vals[i] !== undefined)
                                out.push(Qt.point(vb.lx + vb.slot * i + vb.slot / 2, vb.ty + vb.ph - vb.ph * vals[i] / Math.max(1e-9, b.vmax) * vb.local(i)))
                            return out
                        }
                    }
                }
            }
            Repeater {
                model: b.line && b.line.dots ? b.line.vals : []
                Rectangle {
                    required property var modelData
                    required property int index
                    visible: modelData !== null && modelData !== undefined
                    width: 7; height: 7; radius: 3.5; color: b.line.color
                    x: vb.lx + vb.slot * index + vb.slot / 2 - 3.5
                    y: vb.ty + vb.ph - vb.ph * (modelData || 0) / Math.max(1e-9, b.vmax) * vb.local(index) - 3.5
                }
            }
            Repeater {
                model: b.hlines || []
                Item {
                    required property var modelData
                    readonly property real hy: vb.yOf(modelData.v)
                    Shape {
                        ShapePath {
                            strokeColor: modelData.color; strokeWidth: 1.5; fillColor: "transparent"
                            strokeStyle: ShapePath.DashLine; dashPattern: [4, 3]
                            startX: vb.lx; startY: hy
                            PathLine { x: vb.lx + vb.pw; y: hy }
                        }
                    }
                    Text { visible: !!modelData.label; x: vb.lx; width: vb.pw - 4; y: hy - 18; horizontalAlignment: Text.AlignRight
                           text: modelData.label || ""; color: modelData.color; font.family: T.font; font.pixelSize: 12; font.bold: true }
                }
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.s.clickable && vb.hover >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                onPositionChanged: function (m) {
                    var i = Math.floor((m.x - vb.lx) / vb.slot)
                    vb.hover = (i >= 0 && i < vb.n && m.y >= vb.ty - 10 && m.y <= vb.ty + vb.ph + 20) ? i : -1
                    var bs = b.bars || []
                    if (vb.hover >= 0 && bs[vb.hover] && bs[vb.hover].tip) {
                        var p = mapToItem(root, m.x, m.y); root.showTip(bs[vb.hover].tip, p.x, p.y)
                    } else root.hideTip()
                }
                onExited: { vb.hover = -1; root.hideTip() }
                onClicked: if (vb.hover >= 0 && root.s.clickable) root.acted(["pick", vb.hover])
            }
        }
    }

    // ---------- History (line / area) ----------
    Component {
        id: cLine
        Item {
            id: ln
            readonly property var b: parent.b
            readonly property var s0: (b.series || [])[0] || ({vals: []})
            readonly property int n: Math.max(1, s0.vals.length - 1)
            readonly property real lx: 66
            readonly property real ty: 6 + (b.legend ? 16 : 0)
            readonly property real pw: width - lx - 8
            readonly property real ph: height - ty - (b.xlabels && b.xlabels.length ? 22 : 8)
            function px(i) { return lx + pw * i / n }
            function py(v) { return ty + ph - ph * v / Math.max(1e-9, b.vmax) }
            property int hover: -1
            Repeater {
                model: b.grid || []
                Item {
                    required property var modelData
                    required property int index
                    readonly property real gy: ln.ty + ln.ph - ln.ph * index / 4
                    Rectangle { x: ln.lx; y: parent.gy; width: ln.pw; height: 1; color: index ? Qt.rgba(1, 1, 1, 0.05) : T.line }
                    Text { x: ln.lx - 64; y: parent.gy - 8; width: 58; horizontalAlignment: Text.AlignRight; text: modelData
                           color: T.dim; font.family: T.font; font.pixelSize: 11 }
                }
            }
            // The curve is built once, whole, and drawn once into its layer; the build-up only uncovers it from the left
            // (a clip that grows). Before, every frame of the 0.9 s build made the path anew – the shape re-triangulated
            // and its 4× smoothed layer redrawn each frame, which stuttered (most of all with software drawing).
            Item {
                id: reveal
                width: ln.lx + ln.pw * root.t + 3; height: parent.height
                clip: true
                Repeater {
                    model: b.series || []
                    Shape {
                        required property var modelData
                        width: ln.width; height: ln.height
                        layer.enabled: true; layer.samples: 4   // smoothed; the curve renderer ignores clipping (scroll areas)
                        id: sh
                        readonly property var pts: {
                            var out = [], v = modelData.vals
                            for (var i = 0; i < v.length; i++) out.push(Qt.point(ln.px(i), ln.py(v[i])))
                            return out
                        }
                        ShapePath {   // area
                            strokeColor: "transparent"
                            fillGradient: LinearGradient { y1: ln.ty; y2: ln.ty + ln.ph
                                GradientStop { position: 0; color: Qt.rgba(Qt.color(modelData.color).r, Qt.color(modelData.color).g, Qt.color(modelData.color).b, modelData.fill ? 0.42 : 0) }
                                GradientStop { position: 1; color: Qt.rgba(Qt.color(modelData.color).r, Qt.color(modelData.color).g, Qt.color(modelData.color).b, modelData.fill ? 0.03 : 0) } }
                            PathPolyline { path: sh.pts.length > 1 ? sh.pts.concat([Qt.point(sh.pts[sh.pts.length - 1].x, ln.ty + ln.ph), Qt.point(ln.lx, ln.ty + ln.ph)]) : [] }
                        }
                        ShapePath {   // line
                            strokeColor: modelData.color; strokeWidth: modelData.fill ? 2.4 : 2; fillColor: "transparent"
                            strokeStyle: modelData.dash ? ShapePath.DashLine : ShapePath.SolidLine; dashPattern: [4, 3]
                            PathPolyline { path: sh.pts }
                        }
                    }
                }
            }
            Repeater {
                model: b.hlines || []
                Item {
                    required property var modelData
                    readonly property real hy: ln.py(modelData.v)
                    Shape { ShapePath { strokeColor: modelData.color; strokeWidth: 2; fillColor: "transparent"; strokeStyle: ShapePath.DashLine; dashPattern: [4, 3]
                                        startX: ln.lx; startY: hy; PathLine { x: ln.lx + ln.pw; y: hy } } }
                    Text { x: ln.lx; width: ln.pw - 4; y: hy - 18; horizontalAlignment: Text.AlignRight; text: modelData.label || ""
                           color: modelData.color; font.family: T.font; font.pixelSize: 12; font.bold: true }
                }
            }
            Repeater {   // vertical ticks: e.g. days when cards were added („+240“)
                model: b.vmarks || []
                Item {
                    required property var modelData
                    readonly property real vx: ln.px(modelData.i)
                    visible: root.t > 0.99
                    Rectangle { x: parent.vx; y: ln.ty; width: 1; height: ln.ph; color: Qt.rgba(1, 0.89, 0.48, 0.35) }
                    Text { x: parent.vx + 4; y: ln.ty + 2; text: modelData.label || ""
                           color: Qt.rgba(1, 0.89, 0.48, 0.8); font.family: T.font; font.pixelSize: 11; font.bold: true }
                }
            }
            Item {
                visible: !!b.marker && root.t > 0.99
                Rectangle { x: ln.px(b.marker ? b.marker.i : 0) - 7; y: ln.py(b.marker ? ln.s0.vals[b.marker.i] : 0) - 7; width: 14; height: 14; radius: 7
                            color: b.marker ? b.marker.color : "transparent" }
                Text { x: ln.px(b.marker ? b.marker.i : 0) + 10; y: ln.py(b.marker ? ln.s0.vals[b.marker.i] : 0) - 26
                       text: b.marker ? b.marker.label : ""; color: b.marker ? b.marker.color : T.text; font.family: T.font; font.pixelSize: 12 }
            }
            Row {
                visible: !!b.legend
                x: ln.lx + 10; y: 0; spacing: 20
                Repeater { model: b.legend || []
                    Row { required property var modelData; spacing: 6
                          Rectangle { width: 14; height: 4; radius: 2; color: modelData.color; anchors.verticalCenter: parent.verticalCenter }
                          Text { text: modelData.text; color: T.muted; font.family: T.font; font.pixelSize: 12 } } }
            }
            Text { visible: !!(b.xlabels && b.xlabels.length); x: ln.lx; y: ln.ty + ln.ph + 4; text: b.xlabels ? b.xlabels[0] : ""
                   color: T.dim; font.family: T.font; font.pixelSize: 11 }
            Text { visible: !!(b.xlabels && b.xlabels.length); anchors.right: parent.right; anchors.rightMargin: 8; y: ln.ty + ln.ph + 4
                   text: b.xlabels ? b.xlabels[b.xlabels.length - 1] : ""; color: T.dim; font.family: T.font; font.pixelSize: 11 }
            Rectangle { visible: ln.hover >= 0; x: ln.px(Math.max(0, ln.hover)); y: ln.ty; width: 1; height: ln.ph; color: Qt.rgba(1, 1, 1, 0.25) }
            Rectangle { visible: ln.hover >= 0; width: 9; height: 9; radius: 4.5; color: ln.s0.color || T.text
                        x: ln.px(Math.max(0, ln.hover)) - 4.5; y: ln.py(ln.hover >= 0 ? ln.s0.vals[ln.hover] : 0) - 4.5 }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onPositionChanged: function (m) {
                    if (m.x < ln.lx || m.x > ln.lx + ln.pw) { ln.hover = -1; root.hideTip(); return }
                    var i = Math.round((m.x - ln.lx) / ln.pw * ln.n)
                    i = Math.max(b.skipFirst ? 1 : 0, Math.min(ln.n, i))
                    ln.hover = i
                    var p = mapToItem(root, m.x, m.y)
                    root.showTip((b.tips || [])[i] || [], p.x, p.y)
                }
                onExited: { ln.hover = -1; root.hideTip() }
            }
        }
    }

    // ---------- Ring ----------
    Component {
        id: cDonut
        Item {
            id: dn
            readonly property var b: parent.b
            readonly property bool narrow: width < 360
            readonly property int np: (b.parts || []).length
            readonly property int lcols: narrow ? 2 : 1
            readonly property real lrh: narrow ? 20 : 30
            readonly property real legendH: Math.ceil(np / lcols) * lrh
            readonly property real d: narrow ? Math.max(40, Math.min(width - 16, height - legendH - 14)) : Math.min(height, width * 0.45) - 8
            readonly property real ring: d * 0.16
            readonly property real cx: narrow ? width / 2 : 8 + d / 2
            readonly property real cy: narrow ? d / 2 + 2 : height / 2
            readonly property real lx: narrow ? 0 : 8 + d + 26
            readonly property real ly: narrow ? d + 12 : Math.max(0, (height - np * 30) / 2)
            readonly property real lw: (width - lx) / lcols
            property int hover: -1
            Repeater {
                model: b.parts || []
                Shape {
                    id: arc
                    required property var modelData
                    required property int index
                    anchors.fill: parent
                    layer.enabled: true; layer.samples: 4   // smoothed; the curve renderer ignores clipping (scroll areas)
                    readonly property real start: { var a = 0, ps = b.parts; for (var i = 0; i < index; i++) a += ps[i].n; return 360 * a / Math.max(1, b.total) }
                    ShapePath {
                        strokeColor: modelData.color; fillColor: "transparent"
                        strokeWidth: dn.ring * (dn.hover === index ? 1.25 : 1); capStyle: ShapePath.FlatCap
                        PathAngleArc { centerX: dn.cx; centerY: dn.cy; radiusX: dn.d / 2 - dn.ring / 2; radiusY: radiusX
                                       startAngle: -90 + arc.start * root.t; sweepAngle: 360 * modelData.n / Math.max(1, b.total) * root.t }
                    }
                }
            }
            Text { x: dn.cx - dn.d / 2; width: dn.d; y: dn.cy - height / 2 - 8; horizontalAlignment: Text.AlignHCenter
                   text: b.center || ""; color: b.centerColor || T.text; font.family: T.display; font.pixelSize: Math.max(16, dn.d / 7) }
            Text { visible: dn.d >= 120; x: dn.cx - dn.d / 2; width: dn.d; y: dn.cy + dn.d * 0.1; horizontalAlignment: Text.AlignHCenter
                   text: b.centerLabel || ""; color: T.muted; font.family: T.font; font.pixelSize: 12 }
            Repeater {
                model: b.parts || []
                Item {
                    required property var modelData
                    required property int index
                    x: dn.lx + (index % dn.lcols) * dn.lw; y: dn.ly + Math.floor(index / dn.lcols) * dn.lrh
                    width: dn.lw - (dn.narrow ? 8 : 0); height: dn.lrh
                    Rectangle { anchors.verticalCenter: parent.verticalCenter; width: 12; height: 12; radius: 3; color: modelData.color }
                    Text { x: 20; width: parent.width - 20 - num.width - 8; height: parent.height; verticalAlignment: Text.AlignVCenter
                           elide: Text.ElideRight; text: modelData.label; color: T.text; font.family: T.font; font.pixelSize: dn.narrow ? 12 : 13 }
                    Text { id: num; anchors.right: parent.right; height: parent.height; verticalAlignment: Text.AlignVCenter
                           text: dn.narrow ? modelData.pct : modelData.n + "  ·  " + modelData.pct; color: T.muted
                           font.family: T.font; font.pixelSize: dn.narrow ? 12 : 13 }
                }
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.s.clickable && dn.hover >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                function partAt(mx, my) {
                    var dx = mx - dn.cx, dy = my - dn.cy, dist = Math.sqrt(dx * dx + dy * dy)
                    var ps = b.parts || []
                    if (dist <= dn.d / 2 + 6 && dist >= dn.d / 2 - dn.ring * 1.3) {
                        var ang = (Math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360, acc = 0
                        for (var i = 0; i < ps.length; i++) { acc += 360 * ps[i].n / Math.max(1, b.total); if (ang < acc) return i }
                        return -1
                    }
                    if (mx >= dn.lx && my >= dn.ly) {
                        var k = Math.floor((my - dn.ly) / dn.lrh) * dn.lcols + Math.min(dn.lcols - 1, Math.floor((mx - dn.lx) / dn.lw))
                        return k >= 0 && k < ps.length ? k : -1
                    }
                    return -1
                }
                onPositionChanged: function (m) {
                    dn.hover = partAt(m.x, m.y)
                    if (dn.hover >= 0) { var p = mapToItem(root, m.x, m.y); root.showTip(b.parts[dn.hover].tip, p.x, p.y) }
                    else root.hideTip()
                }
                onExited: { dn.hover = -1; root.hideTip() }
                onClicked: if (dn.hover >= 0 && root.s.clickable) root.acted(["pick", dn.hover])
            }
        }
    }

    // ---------- horizontal bars ----------
    Component {
        id: cHBars
        Item {
            id: hb
            readonly property var b: parent.b
            readonly property int n: (b.rows || []).length
            readonly property bool narrow: width < 340
            readonly property real rh: Math.min(narrow ? 40 : 30, height / Math.max(1, n))
            readonly property real lw: narrow ? 0 : Math.min(width * 0.42, 260)
            readonly property real tw: narrow ? 40 : 90
            property int hover: -1
            Repeater {
                model: b.rows || []
                Item {
                    required property var modelData
                    required property int index
                    y: index * hb.rh; width: hb.width; height: hb.rh
                    readonly property real lv: root.ease(root.t * 1.5 - index * 0.05)
                    Text { width: hb.narrow ? hb.width : hb.lw - 10; height: hb.narrow ? 18 : parent.height; verticalAlignment: Text.AlignVCenter
                           elide: Text.ElideRight; text: modelData.label; color: T.text; font.family: T.font; font.pixelSize: hb.narrow ? 12 : 13 }
                    Rectangle {
                        id: hbar
                        x: hb.lw; y: hb.narrow ? 20 : parent.height * 0.22; height: hb.narrow ? Math.max(6, parent.height - 26) : parent.height * 0.56
                        width: Math.max(2, (hb.width - hb.lw - hb.tw) * modelData.v / Math.max(1e-9, b.vmax) * parent.lv)
                        radius: height / 2
                        gradient: Gradient { orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: b.bottom || Qt.darker(b.color, 2) }
                            GradientStop { position: 1; color: b.color } }
                        border.width: hb.hover === index ? 1 : 0; border.color: b.color
                    }
                    Text { x: hbar.x + hbar.width + 8; y: hbar.y + hbar.height / 2 - height / 2; verticalAlignment: Text.AlignVCenter
                           text: modelData.text; color: b.color; font.family: T.font; font.pixelSize: 13 }
                }
            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: root.s.clickable && hb.hover >= 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                onPositionChanged: function (m) {
                    var i = Math.floor(m.y / hb.rh)
                    hb.hover = i >= 0 && i < hb.n ? i : -1
                    var rows = b.rows || []
                    if (hb.hover >= 0 && rows[hb.hover].tip.length) { var p = mapToItem(root, m.x, m.y); root.showTip(rows[hb.hover].tip, p.x, p.y) }
                    else root.hideTip()
                }
                onExited: { hb.hover = -1; root.hideTip() }
                onClicked: if (hb.hover >= 0 && root.s.clickable) root.acted(["pick", hb.hover])
            }
        }
    }

    // ---------- Stream: tiles and list ----------
    Component {
        id: cTiles
        Row {
            spacing: 10
            readonly property var items: parent.b.items || []
            readonly property real tw: (width - 10 * Math.max(0, items.length - 1)) / Math.max(1, items.length)
            width: parent.width; height: parent.height
            Repeater {
                model: parent.items
                Rectangle {
                    required property var modelData
                    width: parent.tw; height: parent.height; radius: 10; color: Qt.darker(T.surface, 1.3)
                    Text { x: 12; y: 8; width: parent.width - 24; elide: Text.ElideRight; text: modelData.label; color: T.muted
                           font.family: T.font; font.pixelSize: 14 }
                    Text { x: 12; anchors.bottom: parent.bottom; anchors.bottomMargin: 8; width: parent.width - 24
                           fontSizeMode: Text.HorizontalFit; minimumPixelSize: 14; font.pixelSize: 26
                           text: modelData.text; color: modelData.color; font.family: T.display; font.bold: true }
                }
            }
        }
    }
    Component {
        id: cList
        Column {
            width: parent.width
            readonly property var rows: parent.b.rows || []
            readonly property real rh: Math.min(30, parent.height / Math.max(1, rows.length))
            Repeater {
                model: parent.rows
                Item {
                    required property var modelData
                    required property int index
                    width: parent.width; height: parent.rh
                    Text { width: 28; height: parent.height; verticalAlignment: Text.AlignVCenter; text: (index + 1) + "."
                           color: T.muted; font.family: T.display; font.pixelSize: 15; font.bold: true }
                    Text { id: lt; x: 30; height: parent.height; verticalAlignment: Text.AlignVCenter
                           width: Math.min(implicitWidth, parent.width - 330); elide: Text.ElideRight
                           text: modelData.text; color: T.text; font.family: T.font; font.pixelSize: 15 }
                    Text { x: lt.x + lt.width + 10; height: parent.height; verticalAlignment: Text.AlignVCenter
                           text: modelData.sub; color: T.muted; font.family: T.font; font.pixelSize: 13 }
                    Text { anchors.right: parent.right; height: parent.height; verticalAlignment: Text.AlignVCenter
                           text: modelData.price; color: modelData.color; font.family: T.display; font.pixelSize: 16; font.bold: true }
                }
            }
        }
    }
}
