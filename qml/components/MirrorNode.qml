// One element of a mirrored form (see qform.py). Containers (row/col/form/grid/group) draw their
// children recursively; input goes back to the real widget via mirror.act(id, wert).
import QtQuick

Item {
    id: n
    property var node: ({})
    property var mirror
    readonly property string t: node && node.t ? node.t : ""
    property var hub: null   // Mirror.qml's key -> node table (its one Connections hands out value changes)
    // values (text, checkmark, number …) come separately from the structure: they change without rebuilding the element.
    // Re-read only when the form names this node's key (valsChanged) – a form-wide rev made every node re-read and
    // re-lay out on each slider step
    property var nv: n.read()
    function read() { return n.mirror && node && node.k !== undefined ? n.mirror.val(node.k) : (node || {}) }
    function enlist() { if (n.hub && n.node && n.node.k !== undefined) n.hub.nodes[n.node.k] = n }
    onNodeChanged: { nv = read(); enlist() }
    onMirrorChanged: nv = read()
    Component.onCompleted: enlist()
    Component.onDestruction: if (n.hub && n.node && n.hub.nodes[n.node.k] === n) delete n.hub.nodes[n.node.k]
    Connections {   // only without a hub: one Connections per node converts the key map once per node (slow)
        target: n.hub ? null : n.mirror
        ignoreUnknownSignals: true
        function onValsChanged(keys) { if (n.node && n.node.k !== undefined && keys[n.node.k] === true) n.nv = n.read() }
    }
    implicitWidth: ld.item && (n.t !== "label" || n.nv.fixed === true) && n.t !== "row" && n.t !== "col" && n.t !== "form" && n.t !== "grid"
                   && n.t !== "group" ? ld.item.implicitWidth : 0
    implicitHeight: ld.item && n.nv.hidden !== true ? ld.item.implicitHeight : 0
    height: implicitHeight
    visible: n.nv.hidden !== true   // empty hint slot (ui.slot_note): no space, no gap

    // Search hit / link target in the settings (node "flash"): scroll it into view and pulse it once – a search hit
    // ("flashStay") blinks twice and stays marked until the mouse is over it (Oliver, review .101 – a7)
    Rectangle {
        id: flashBox
        readonly property bool on: n.nv.flash === true
        readonly property bool stay: n.nv.flashStay === true
        property bool held: false   // blinked, now marked until hovered
        z: -1; anchors.fill: parent; anchors.margins: -6; radius: 8
        color: T.surface2; border.width: 1; border.color: T.text2
        opacity: 0
        onOnChanged: if (on) Qt.callLater(go)
        Component.onCompleted: if (on) Qt.callLater(go)
        function go() {
            for (var p = n.parent; p; p = p.parent)
                if (p.contentY !== undefined && p.contentItem !== undefined) {
                    var y = n.mapToItem(p.contentItem, 0, 0).y
                    p.contentY = Math.max(0, Math.min(y - 80, p.contentHeight - p.height))
                    break
                }
            if (stay) blinkTwice.restart(); else blink.restart()
        }
        SequentialAnimation {
            id: blink
            PauseAnimation { duration: 260 }   // the page has arrived first
            NumberAnimation { target: flashBox; property: "opacity"; to: 1; duration: 220; easing.type: Easing.OutCubic }
            NumberAnimation { target: flashBox; property: "opacity"; to: 0; duration: 900; easing.type: Easing.InOutCubic }
        }
        SequentialAnimation {
            id: blinkTwice
            PauseAnimation { duration: 260 }
            NumberAnimation { target: flashBox; property: "opacity"; to: 1; duration: 160 }
            NumberAnimation { target: flashBox; property: "opacity"; to: 0.15; duration: 160 }
            NumberAnimation { target: flashBox; property: "opacity"; to: 1; duration: 160 }
            NumberAnimation { target: flashBox; property: "opacity"; to: 0.15; duration: 160 }
            NumberAnimation { target: flashBox; property: "opacity"; to: 1; duration: 160 }
            ScriptAction { script: { flashBox.held = true; if (seenHover.hovered) flashBox.seen() } }
        }
        NumberAnimation { id: fadeOut; target: flashBox; property: "opacity"; to: 0; duration: 600; easing.type: Easing.InOutCubic }
        function seen() {
            held = false
            fadeOut.restart()
            if (typeof settingsPage !== "undefined" && settingsPage.flashSeen) settingsPage.flashSeen()
        }
        // the mouse over the setting (after the blinking): the mark fades
        HoverHandler { id: seenHover; enabled: flashBox.held; onHoveredChanged: if (hovered && flashBox.held) flashBox.seen() }
    }

    Loader {
        id: ld
        width: n.width
        sourceComponent: n.t === "label" ? cLabel : n.t === "button" ? cButton : n.t === "check" ? cCheck
                       : n.t === "combo" ? cCombo : n.t === "spin" ? cSpin : n.t === "edit" ? cEdit
                       : n.t === "row" ? cRow : n.t === "col" ? cCol : n.t === "form" ? cForm
                       : n.t === "grid" ? cGrid : n.t === "group" ? cGroup : n.t === "line" ? cLine
                       : n.t === "stretch" ? cStretch : n.t === "list" ? cList : n.t === "textarea" ? cTextArea
                       : n.t === "slider" ? cSlider : n.t === "progress" ? cProgress
                       : n.t === "image" ? cImage : n.t === "tabs" ? cTabs : n.t === "chart" ? cChart
                       : n.t === "camera" ? cCamera : n.t === "table" ? cTable : n.t === "pixel" ? cPixel
                       : n.t === "datetime" ? cDateTime : n.t === "tags" ? cTags : n.t === "space" ? cSpace : n.t === "cards" ? cCards
                       : n.t === "swatch" ? cSwatch : n.t === "scroll" ? cScroll : n.t === "picker" ? cPicker : n.t === "checklist" ? cCheckList : n.t === "game" ? cGame : n.t === "fortune" ? cFortune : n.t === "tag" ? cTag : n.t === "orbit" ? cOrbit : null
    }

    Component {
        id: cLabel
        Text {
            // links in the text colour, only underlined (greyscale – no blue); RichText ignores linkColor
            text: n.nv.rich ? (n.nv.html || "").replace(/<a /g, "<a style='color:" + color + "' ") : (n.nv.html || "")
            textFormat: n.nv.rich ? Text.RichText : Text.PlainText
            wrapMode: n.nv.wrap ? Text.Wrap : Text.NoWrap
            elide: n.nv.wrap || n.nv.fixed ? Text.ElideNone : Text.ElideRight
            color: n.nv.color && n.nv.color !== "gray" ? n.nv.color : (n.nv.color === "gray" ? T.muted : T.text2)
            font.family: n.nv.font || T.font; font.pixelSize: n.nv.px || (n.nv.big ? 16 : 13); font.bold: n.nv.bold === true
            onLinkActivated: function (link) { Qt.openUrlExternally(link) }
            // Text with a set width works out its own height only when first asked – and reports the change during
            // that very query (binding loop in n.implicitHeight). Ask once here, before n reads it.
            Component.onCompleted: implicitHeight
        }
    }
    Component {
        id: cButton
        Btn {
            text: n.nv.text || ""
            glyph: n.nv.glyph || ""
            compact: true
            height: 30
            enabled: n.nv.enabled !== false
            danger: n.nv.danger === true
            active: n.nv.active === true || !!(n.nv.checkable && n.nv.checked)
            primary: n.nv.primary === true
            checkable: n.nv.checkable === true
            ledAlways: n.nv.checkable === true   // choice with a little lamp: off grey, on white
            tip: n.nv.tip || ""
            onClicked: n.mirror.act(n.nv.id, null)
        }
    }
    Component {   // tag: outlined, transparent (condition, finish …) – click cycles through
        id: cTag
        Rectangle {
            implicitWidth: tagT.implicitWidth + (n.nv.plain ? 4 : 16); implicitHeight: 24
            radius: 6; color: "transparent"
            border.width: n.nv.plain ? 0 : 1.2   // plain: text only (finish), outlined = condition
            border.color: tagH.hovered && n.nv.click ? T.text : (n.nv.on === false ? T.line2 : T.text2)
            Behavior on border.color { ColorAnimation { duration: 140 } }
            Text { id: tagT; anchors.centerIn: parent; text: n.nv.text || ""
                   color: tagH.hovered && n.nv.click ? T.text : (n.nv.on === false ? T.dim : T.text2)
                   font.family: T.font; font.pixelSize: n.nv.plain ? 13 : 12; font.bold: !n.nv.plain
                   font.underline: n.nv.plain === true && tagH.hovered && n.nv.click === true }
            HoverHandler { id: tagH; cursorShape: n.nv.click ? Qt.PointingHandCursor : Qt.ArrowCursor
                           onHoveredChanged: if (hovered && n.nv.tip) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 2); shell.tip(n.nv.tip, p.x, p.y) }
                                             else shell.tip("", 0, 0) }
            TapHandler { enabled: n.nv.click === true; onTapped: n.mirror.act(n.nv.id, null) }
        }
    }
    Component {
        id: cCheck
        CheckBox {
            text: n.nv.text || ""
            checked: n.nv.checked === true
            enabled: n.nv.enabled !== false
            tip: n.nv.tip || ""
            onToggled: function (on) { n.mirror.act(n.nv.id, on) }
        }
    }
    Component {
        id: cCombo
        DropList {
            height: 32
            minWidth: 90
            items: { var out = []; var it = n.nv.items || []; for (var i = 0; i < it.length; i++) out.push({key: "" + i, text: it[i]}); return out }
            current: "" + n.nv.index
            enabled: n.nv.enabled !== false
            onPicked: function (k) { n.mirror.act(n.nv.id, parseInt(k)) }
        }
    }
    Component {
        id: cSpin
        SpinField {
            width: 120
            value: n.nv.value || 0; from: n.nv.min || 0; to: n.nv.max !== undefined ? n.nv.max : 100; step: n.nv.step || 1
            decimals: n.nv.decimals || 0; suffix: n.nv.suffix || ""; prefix: n.nv.prefix || ""
            enabled: n.nv.enabled !== false
            onCommitted: function (v) { n.mirror.act(n.nv.id, v) }
        }
    }
    Component {
        id: cEdit
        SearchField {
            height: 32
            text: n.nv.text || ""
            placeholder: n.nv.placeholder || ""
            clearable: false
            enabled: n.nv.enabled !== false
            onEdited: function (t) { n.mirror.act(n.nv.id, ["live", t]) }   // typed text stays (values keep updating)
            onAccepted: n.mirror.act(n.nv.id, text)
            onActiveFocusChanged: if (!activeFocus) n.mirror.act(n.nv.id, text)
            Component.onCompleted: if (n.nv.focus) focusAll()
        }
    }
    Component {
        id: cRow
        Item {
            implicitHeight: row.implicitHeight
            Row {
                id: row
                x: 0
                width: parent.width - x
                spacing: Math.max(6, n.nv.spacing || 8)
                readonly property var kids: n.node.items || []
                // tall elements (columns, groups, tables …) align to the top, otherwise centred (text next to field)
                readonly property bool alignTop: {
                    var tall = ["col", "form", "group", "grid", "table", "list", "textarea", "camera", "chart", "cards", "pixel", "scroll", "picker", "checklist", "game"]
                    for (var i = 0; i < kids.length; i++) if (kids[i] && tall.indexOf(kids[i].t) >= 0) return true
                    return false
                }
                // width: fixed elements take their width, texts and spacers share the rest
                readonly property real fixedW: {
                    // over the real children of the row (the list reports new children, their widths report changes) –
                    // via rep.itemAt the binding missed buttons that loaded later: buttons on the right slid out
                    var w = 0, cs = row.children
                    for (var i = 0; i < cs.length; i++) {
                        var c = cs[i]
                        if (c.nd === undefined || row.isFlex(c.nd)) continue
                        w += c.width
                    }
                    return w + spacing * Math.max(0, kids.length - 1)
                }
                function isFlex(k) {
                    var t = k ? k.t : ""
                    if (t === "label") { try { if (n.mirror.val(k.k).fixed) return false } catch (e) {} }
                    return t === "label" || t === "stretch" || t === "slider" || t === "line" || t === "row" || t === "col" || t === "list" || t === "textarea"
                        || t === "progress" || t === "form" || t === "grid" || t === "group" || t === "chart" || t === "camera"
                        || t === "table" || t === "datetime" || t === "tags" || t === "cards" || t === "picker" || t === "checklist" || t === "orbit"
                        || (t === "edit")
                }
                function weight(k) { try { var v = n.mirror.val(k.k); return v && v.w ? v.w : 1 } catch (e) { return 1 } }
                readonly property real flex: {
                    var c = 0; for (var i = 0; i < kids.length; i++) if (isFlex(kids[i])) c += weight(kids[i])
                    return Math.max(1, c)
                }
                Repeater {
                    id: rep
                    model: row.kids
                    delegate: Child {
                        required property var modelData
                        nd: modelData
                        flexW: row.isFlex(modelData) ? Math.max(0, (row.width - row.fixedW) / row.flex * row.weight(modelData)) : -1
                        anchors.verticalCenter: parent && !row.alignTop ? parent.verticalCenter : undefined
                    }
                }
            }
        }
    }
    Component {
        id: cCol
        Column {
            x: 0
            width: n.width - x
            spacing: Math.max(4, n.nv.spacing || 6)
            Repeater {
                model: n.node.items || []
                delegate: Child { required property var modelData; nd: modelData; flexW: parent ? parent.width : 0 }
            }
        }
    }
    Component {   // fixed height, content scrolls
        id: cScroll
        Flickable {
            id: sfl
            ScrollHint {}
            width: n.width
            implicitHeight: Math.min(n.nv.h || 300, scol.implicitHeight)
            height: implicitHeight
            contentWidth: width; contentHeight: scol.implicitHeight
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: scol
                width: sfl.width - 12
                spacing: Math.max(4, n.nv.spacing || 6)
                Repeater {
                    model: n.node.items || []
                    delegate: Child { required property var modelData; nd: modelData; flexW: scol.width }
                }
            }
        }
    }
    Component {
        id: cForm
        Column {
            width: n.width
            spacing: 8
            Repeater {
                model: n.node.items || []
                delegate: Item {
                    required property var modelData
                    width: parent.width
                    height: Math.max(lab.implicitHeight, fld.implicitHeight)
                    // label narrow, single fields not across the full width – stays together
                    readonly property bool single: ["combo", "spin", "edit", "slider", "datetime"].indexOf((modelData.field || {}).t) >= 0
                    Child { id: lab; nd: modelData.label || {}; flexW: modelData.field ? Math.min(170, parent.width * 0.32) : parent.width
                            anchors.verticalCenter: parent.verticalCenter }
                    Child { id: fld; nd: modelData.field || {}
                            x: modelData.label ? lab.width + 12 : 0
                            flexW: parent.single ? Math.min(Math.max(340, fld.item ? fld.item.implicitWidth : 0), parent.width - x) : parent.width - x
                            anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
    }
    Component {
        id: cGrid
        Grid {
            width: n.width
            columns: n.node.cols || 1
            columnSpacing: 12; rowSpacing: 6
            Repeater {
                model: (n.node.cells || []).slice().sort(function (a, b) { return a.r - b.r || a.c - b.c })
                delegate: Child { required property var modelData; nd: modelData.node
                                  flexW: (n.width - 12 * ((n.node.cols || 1) - 1)) / (n.node.cols || 1) }
            }
        }
    }
    Component {
        id: cGroup
        Rectangle {
            width: n.width
            readonly property bool titled: !!n.nv.title || n.nv.id !== undefined
            readonly property bool flat: n.nv.flat === true   // no box: divider + heading
            readonly property real pad: flat ? 0 : 20
            // more air inside: 20 px at the sides, equal at top/bottom (previously only 6 px at the bottom)
            implicitHeight: col.implicitHeight + (flat ? (titled ? 50 : 16) : (titled ? 62 : 36))
            radius: Math.min(16, T.panelRadius)
            color: flat ? "transparent" : Qt.darker(T.surface, 1.0)
            border.width: flat ? 0 : 1; border.color: T.line
            Rectangle { visible: parent.flat; width: parent.width; height: 1; color: T.line }
            Row {
                x: parent.pad; y: parent.flat ? 16 : 16; spacing: 8
                visible: parent.titled
                CheckBox { visible: n.nv.id !== undefined; checked: n.nv.checked === true; text: ""
                           onToggled: function (on) { n.mirror.act(n.nv.id, on) } }
                Text { text: n.nv.title || ""; color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
                Lamp { visible: n.nv.lamp === true; anchors.verticalCenter: parent.verticalCenter }
            }
            Column {
                id: col
                x: parent.pad; y: parent.titled ? (parent.flat ? 42 : 44) : (parent.flat ? 14 : 18)
                width: parent.width - 2 * parent.pad
                spacing: 8
                Repeater {
                    model: n.node.items || []
                    delegate: Child { required property var modelData; nd: modelData; flexW: parent ? parent.width : 0 }
                }
            }
        }
    }
    // child element: via a Loader (QML does not allow an element that directly contains itself)
    component Child: Loader {
        id: ch
        property var nd: ({})
        property real flexW: -1
        width: flexW >= 0 ? flexW : (item ? item.implicitWidth : 0)
        height: item ? item.implicitHeight : 0
        Component.onCompleted: setSource(Qt.resolvedUrl("MirrorNode.qml"), {node: ch.nd, mirror: n.mirror, hub: n.hub})
        onNdChanged: if (item) item.node = nd
        onLoaded: item.width = Qt.binding(function () { return ch.width })
    }
    Component {
        id: cList
        Rectangle {
            implicitHeight: Math.min(n.nv.h || 200, lv.contentHeight + 10)
            radius: 10; color: Qt.darker(T.surface, 1.15); border.width: 1; border.color: T.line
            ListView {
                ScrollHint {}
                id: lv
                anchors.fill: parent; anchors.margins: 5
                clip: true; boundsBehavior: Flickable.StopAtBounds
                model: n.nv.items || []
                delegate: Rectangle {
                    required property var modelData
                    width: lv.width; height: 32; radius: 7
                    color: modelData.sel ? T.accent_deep : (lh.hovered && modelData.enabled ? T.button : "transparent")
                    Row {
                        x: 8; anchors.verticalCenter: parent.verticalCenter; spacing: 8
                        // display only – the whole row toggles the checkmark (else checkmark and row both fired)
                        CheckBox { visible: modelData.checkable; checked: modelData.checked; text: ""; interactive: false }
                        Text { text: modelData.text; color: modelData.enabled ? T.text : T.dim; font.family: T.font
                               font.pixelSize: 13; anchors.verticalCenter: parent.verticalCenter }
                    }
                    HoverHandler { id: lh; cursorShape: modelData.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
                    TapHandler {
                        gesturePolicy: TapHandler.ReleaseWithinBounds
                        enabled: modelData.enabled
                        onTapped: n.mirror.act(n.nv.id, modelData.checkable ? ["check", modelData.row, !modelData.checked]
                                                                            : ["click", modelData.row])
                        onDoubleTapped: n.mirror.act(n.nv.id, ["double", modelData.row])
                    }
                }
            }
        }
    }
    Component {
        id: cTextArea
        Rectangle {
            implicitHeight: n.nv.h || 120
            radius: 10; color: Qt.darker(T.surface, 1.15); border.width: 1; border.color: ta.activeFocus ? T.line2 : T.line
            Flickable {
                id: taF
                ScrollHint {}
                anchors.fill: parent; anchors.margins: 8
                contentHeight: ta.height; clip: true
                TextEdit {
                    id: ta
                    width: parent.width
                    height: Math.max(implicitHeight, taF.height)   // whole area clickable, not just the first line
                    text: n.nv.text || ""
                    readOnly: n.nv.readOnly === true
                    wrapMode: TextEdit.Wrap
                    color: T.text; selectionColor: T.line2; font.family: T.font; font.pixelSize: 13
                    selectByMouse: true
                    activeFocusOnTab: !readOnly
                    // Tab moves on (as in the single-line fields) instead of typing a tab character
                    Keys.onTabPressed: function (e) { var x = ta.nextItemInFocusChain(true); if (x) x.forceActiveFocus(Qt.TabFocusReason) }
                    Keys.onBacktabPressed: function (e) { var x = ta.nextItemInFocusChain(false); if (x) x.forceActiveFocus(Qt.BacktabFocusReason) }
                    onTextChanged: if (activeFocus && !readOnly) n.mirror.act(n.nv.id, ["live", text])
                    onActiveFocusChanged: if (!activeFocus && !readOnly) n.mirror.act(n.nv.id, text)
                }
                Text { visible: ta.text === ""; text: n.nv.placeholder || ""; color: T.dim; font.family: T.font
                       font.pixelSize: 13; width: parent.width; wrapMode: Text.Wrap }
            }
        }
    }
    Component {
        id: cSlider
        StepSlider {
            implicitWidth: 220
            from: n.nv.min || 0; to: n.nv.max || 0; value: n.nv.value || 0; showNumber: ((n.nv.max || 0) - (n.nv.min || 0)) <= 20
            onMoved: function (v) { n.mirror.act(n.nv.id, v) }
        }
    }
    Component {
        id: cProgress
        Item {
            implicitHeight: 22
            Rectangle { anchors.verticalCenter: parent.verticalCenter; width: parent.width; height: 8; radius: 4; color: T.button
                Rectangle { height: parent.height; radius: 4; color: T.accent
                            width: parent.width * Math.max(0, Math.min(1, (n.nv.value - n.nv.min) / Math.max(1, n.nv.max - n.nv.min))) } }
        }
    }
    Component {
        id: cChart
        ChartView {
            implicitHeight: n.nv.h || 200
            spec: n.nv.spec || ({})
            onActed: function (v) { n.mirror.act(n.nv.id, v) }
        }
    }
    Component {
        id: cCamera
        LiveView {
            implicitHeight: n.nv.h || (n.nv.lv === "overlay" && overlayView ? width / overlayView.aspect
                                                                             : Math.max(260, Math.min(560, width * 9 / 16)))
            lv: n.nv.lv === "preview" ? previewView : (n.nv.lv === "overlay" ? overlayView : null)
        }
    }
    Component {
        id: cTable
        DataTable {
            implicitHeight: n.nv.h || 220
            cols: n.nv.cols || []
            rows: n.nv.rows || []
            sel: n.nv.sel !== undefined ? n.nv.sel : -1
            empty: n.nv.empty || ""
            onClicked: function (r) { n.mirror.act(n.nv.id, ["click", r]) }
            onDoubleClicked: function (r) { n.mirror.act(n.nv.id, ["double", r]) }
        }
    }
    Component {
        id: cFortune   // Fortune Card (FortuneCard.qml), anchored right – the slip unrolls to the left
        Item {
            implicitHeight: fc.implicitHeight; implicitWidth: fc.implicitWidth
            FortuneCard { id: fc; anchors.right: parent.right; quote: n.nv.quote || "Pack it, rip it, hit it!" }
        }
    }
    Component {
        id: cGame   // Scalper Invaders (scalper.py) – at most 480 wide, centred
        Item {
            implicitHeight: game.height
            ScalperGame {
                id: game
                width: Math.min(480, n.width); anchors.horizontalCenter: parent.horizontalCenter
                ship: n.nv.ship || ""; sprites: n.nv.sprites || ({}); best: n.nv.best || 0
                onNewBest: function (s) { n.mirror.act(n.nv.id, ["best", s]) }
            }
        }
    }
    Component {
        id: cOrbit   // Bent°Corner Orbit (OrbitSlider.qml) – full width of its column
        OrbitSlider {
            width: n.width
            level: n.nv.level === undefined ? 1 : n.nv.level
            compact: n.nv.compact || false
            names: n.nv.names || []; lines: n.nv.lines || []; outs: n.nv.outs || []; points: n.nv.points || [[], [], []]
            terms: n.nv.terms || ""; foot: n.nv.foot || ""; privacy: n.nv.privacy || ""
            moreText: n.nv.more || "More"; lessText: n.nv.less || "Less"
            leaveNote: n.nv.leave || ""
            confirm: n.nv.confirm === true; leaveAsk: n.nv.leaveAsk || ""; stayText: n.nv.stay || ""; leaveText: n.nv.leaveBtn || ""
            onDecided: function (leave) { n.mirror.act(n.nv.id, [leave ? "leave" : "stay"]) }
            onPicked: function (lv) { n.mirror.act(n.nv.id, [lv]) }
        }
    }
    Component {
        id: cPixel
        PixelEditor {
            back: n.nv.back || ""
            presets: n.nv.presets || []
            onEdited: function (b) { n.mirror.act(n.nv.id, ["set", b]) }
        }
    }
    Component {
        id: cPicker
        PickGrid {
            items: n.nv.items || []
            placeholder: n.nv.placeholder || ""
            tileW: n.nv.tileW || 96
            maxH: n.nv.h || 360
            onToggled: function (id, on) { n.mirror.act(n.nv.id, [id, on]) }
            onSetAll: function (on) { n.mirror.act(n.nv.id, ["*", on]) }
        }
    }
    Component {
        id: cCheckList
        CheckList {
            items: n.nv.items || []
            placeholder: n.nv.placeholder || ""
            maxH: n.nv.h || 420
            onToggled: function (id, on) { n.mirror.act(n.nv.id, [id, on]) }
            onSetAll: function (on) { n.mirror.act(n.nv.id, ["*", on]) }
            onExpand: function (id) { n.mirror.act(n.nv.id, ["open", id]) }
        }
    }
    Component {
        id: cDateTime
        DateTimeField {
            value: n.nv.value || ""
            loc: n.nv.loc || "de_DE"
            onChanged: function (v) { n.mirror.act(n.nv.id, v) }
        }
    }
    Component {
        id: cTags
        TagField {
            tags: n.nv.tags || []
            suggestions: n.nv.suggestions || []
            placeholder: n.nv.placeholder || ""
            onAdded: function (t) { n.mirror.act(n.nv.id, ["add", t]) }
            onRemoved: function (t) { n.mirror.act(n.nv.id, ["remove", t]) }
        }
    }
    Component {
        id: cCards
        CardStrip {
            tileH: n.nv.th || 230
            model: n.nv.items || []
            current: n.nv.cur === undefined ? -1 : n.nv.cur
            onPicked: function (i) { n.mirror.act(n.nv.id, i) }
        }
    }
    Component {
        id: cSwatch
        Rectangle {
            implicitWidth: 48; implicitHeight: 24; radius: 6
            color: n.nv.color || "transparent"
            border.width: 1; border.color: sw.hovered ? T.text : T.line2
            HoverHandler { id: sw; cursorShape: Qt.PointingHandCursor
                           onHoveredChanged: if (hovered && n.nv.tip) shell.tip(n.nv.tip, 0, 0); else shell.tip("", 0, 0) }
            TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: n.mirror.act(n.nv.id, null) }
        }
    }
    Component {
        id: cImage
        Item {
            implicitWidth: n.nv.w || 0
            implicitHeight: n.width > 0 && (n.nv.w || 0) > n.width ? (n.nv.h || 0) * n.width / n.nv.w : (n.nv.h || 0)
            Image {
                id: imgN
                anchors.fill: parent
                source: n.nv.url || ""
                cache: false
                fillMode: Image.PreserveAspectFit
                horizontalAlignment: Image.AlignLeft
                smooth: true; mipmap: true
                // with link: lift slightly on hover (like a sticker), click opens the browser
                scale: n.nv.link && imgH.hovered ? 1.04 : 1
                transformOrigin: Item.Left
                Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            }
            HoverHandler { id: imgH; enabled: !!n.nv.link; cursorShape: Qt.PointingHandCursor
                           onHoveredChanged: {
                               if (hovered && n.nv.tip) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 4); shell.tip(n.nv.tip, p.x, p.y) }
                               else shell.tip("", 0, 0)
                           } }
            TapHandler { enabled: !!n.nv.link; onTapped: Qt.openUrlExternally(n.nv.link) }
        }
    }
    Component {
        id: cTabs
        Column {
            width: n.width
            spacing: 10
            Row {
                spacing: 6
                Repeater {
                    model: n.nv.tabs || []
                    Btn { required property var modelData
                          required property int index
                          height: 32; width: Math.max(90, implicitWidth); compact: true; text: modelData
                          checkable: true; checked: index === n.nv.index
                          onClicked: n.mirror.act(n.nv.id, index) }
                }
            }
            Repeater {
                model: n.node.items || []
                delegate: Child { required property var modelData; nd: modelData; flexW: n.width }
            }
        }
    }
    Component { id: cLine; Rectangle { width: n.width; implicitHeight: 1; color: T.line } }
    Component { id: cStretch; Item { implicitHeight: 1; implicitWidth: 0 } }
    Component { id: cSpace; Item { implicitHeight: n.nv.h || 8; implicitWidth: 0 } }
}
