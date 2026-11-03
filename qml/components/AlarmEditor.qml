// Edit price alarm – right in the row, no dialog: expands softly when key is in ta.alarmOpenKeys.
// Several can be open; each stays open until you close it yourself (Save / Cancel / ✎).
// The frame (row + editor as one bright box) is drawn by the caller; here only the content:
//   What     wanted card: cheapest print or exactly one print (bar of all prints) · trade card: your copy
//   Price    Cardmarket / TCGplayer · daily price / Ø 7 / Ø 30 days · normal / foil
//   Limits   drops below / rises above (lists: by %) – Save, Cancel, Delete
//   right    everything we know about the prices of the shown print, and its history (if wide enough)
// Data: ta.alarmFormOf(key) (see qtrade.alarmFormOf).
import QtQuick

Item {
    id: ed
    property var tp
    readonly property var ta: tradeAlarms   // TRADE-SPLIT: AlarmsBackend
    property string key
    property color fadeColor: Qt.darker(T.surface, 1.1)   // colour behind the editor (soft edge of the print bar)
    readonly property bool open: key !== "" && ta.alarmOpenKeys.indexOf(key) >= 0
    readonly property var f: open ? ta.alarmFormOf(key, ta.alarmRev) : ({})
    readonly property bool wide: width >= 760
    readonly property real leftW: Math.min(560, (width - 42) * 0.52)
    // does the print bar need the full width? (many prints) – otherwise it stays left and the prices move up
    readonly property bool stripFull: !wide   // wide: prints left (scroll sideways), prices right from the top
    property bool aOn: false
    property real aVal: 0
    property bool bOn: false
    property real bVal: 0
    property string lastKey: ""
    onFChanged: if (f && f.a && f.key !== lastKey) {   // take over limits only when opening, not on every option
        lastKey = f.key; aOn = f.a.on; aVal = f.a.value; bOn = f.b.on; bVal = f.b.value }
    onOpenChanged: if (!open) lastKey = ""

    width: parent ? parent.width : 400
    height: open ? bodyLd.height + 6 : 0
    property bool instant: false   // e.g. a list row being reused for another entry: jump, don't animate
    Behavior on height { enabled: shell.animate && !ed.instant; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
    clip: true
    visible: height > 0.5

    component Head: Text {
        color: T.muted; font.family: T.font; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.2
    }
    component Line: Row {
        id: ln
        property var d: ({})
        property bool on: false
        property real val: 0
        property real avail: 400
        signal setOn(bool v)
        signal setVal(real v)
        spacing: 12
        CheckBox { width: Math.min(200, ln.avail - 162); anchors.verticalCenter: parent.verticalCenter; text: ln.d.label || ""; checked: ln.on
                   onToggled: function (v) { ln.setOn(v) } }
        SpinField { width: 150; height: 32; anchors.verticalCenter: parent.verticalCenter
                    value: ln.val; from: ln.d.from || 0; to: ln.d.to || 1; step: ln.d.step || 1; decimals: ln.d.dec || 0
                    suffix: ln.d.unit || ""
                    onCommitted: function (v) { ln.setVal(v); ln.setOn(true) } }
    }

    Loader {   // the content only while open or closing (otherwise it sits hidden in every alarm row)
        id: bodyLd
        width: parent.width
        active: ed.open || ed.height > 0.5
        onLoaded: item.shownIn = true   // (after the build, so that it still fades in)
        sourceComponent: Item {
        id: body
        property bool shownIn: false
        height: Math.max(left.y + left.implicitHeight, rightCol.visible ? rightCol.y + rightCol.implicitHeight : 0) + 12
        opacity: ed.open && shownIn ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }

        // ---- what: across the full width (the prints need the space) ----
        Column {
            id: topCol
            x: 14; y: 6
            // if the prints fit in the left column, „What“ stays left and the right side moves up (more compact)
            width: ed.stripFull ? parent.width - 28 : left.width
            spacing: 10
            Head { visible: !ed.f.list; text: shell.text("WHAT") }
            Seg {
                visible: ed.f.kind === "wish"
                items: [{"key": "cheapest", "text": shell.text("cheapest printing")}, {"key": "print", "text": shell.text("one exact printing")}]
                current: ed.f.mode || "cheapest"
                onPicked: function (k) { ed.ta.setAlarmOptOf(ed.key, "mode", k) }
            }
            PrintPicker {
                visible: ed.f.kind === "wish" && ed.f.mode === "print"
                width: parent.width
                searchFrom: 11
                fadeColor: ed.fadeColor
                prints: visible ? (ed.f.prints || []) : []
                onPicked: function (id) { ed.ta.setAlarmOptOf(ed.key, "psid", id); ed.ta.alarmShowPrint(id) }
            }
            Text { visible: !ed.f.list && (ed.f.shown || "") !== ""; width: parent.width; elide: Text.ElideRight
                   text: (ed.f.kind === "trade" ? shell.text("Your copy") : (ed.f.mode === "print" ? shell.text("Chosen") : shell.text("Cheapest right now")))
                         + ": " + ed.f.shown + "  ·  " + shell.text("Now") + " " + (ed.f.now || "")
                   color: T.text2; font.family: T.font; font.pixelSize: 13 }
        }
        Column {
            id: left
            x: 14; y: topCol.y + topCol.implicitHeight + (topCol.implicitHeight > 0 ? 14 : 0)
            width: ed.wide ? ed.leftW : parent.width - 28
            spacing: 10
            // ---- which price ----
            Head { text: shell.text("WHICH PRICE") }
            component PRow: Row {
                property string label
                spacing: 10
                Text { width: 82; anchors.verticalCenter: parent.verticalCenter; text: parent.label
                       color: T.muted; font.family: T.font; font.pixelSize: 12 }
            }
            PRow { label: shell.text("Platform")
                   Seg { items: ed.f.sources || []; current: ed.f.src || "cm"; onPicked: function (k) { ed.ta.setAlarmOptOf(ed.key, "src", k) } } }
            PRow { label: shell.text("Price type")
                   Seg { items: ed.f.bases || []; current: ed.f.basis || "day"; onPicked: function (k) { ed.ta.setAlarmOptOf(ed.key, "basis", k) } } }
            PRow { label: shell.text("Finish"); visible: ed.f.kind !== "trade" && ed.f.kind !== "have"
                   Seg { items: ed.f.finishes || []; current: ed.f.finish || "any"; onPicked: function (k) { ed.ta.setAlarmOptOf(ed.key, "finish", k) } } }
            // ---- Limits ----
            Head { text: shell.text("ALERT WHEN") }
            Line { avail: left.width; d: ed.f.a || ({}); on: ed.aOn; val: ed.aVal
                   onSetOn: function (v) { ed.aOn = v }; onSetVal: function (v) { ed.aVal = v } }
            Line { avail: left.width; d: ed.f.b || ({}); on: ed.bOn; val: ed.bVal
                   onSetOn: function (v) { ed.bOn = v }; onSetVal: function (v) { ed.bVal = v } }
            Text { width: parent.width; wrapMode: Text.Wrap; text: ed.f.note || ""
                   color: T.dim; font.family: T.font; font.pixelSize: 12 }
            Row {
                spacing: 8
                Btn { height: 32; width: Math.min(130, (left.width - 16) / 3); compact: true; text: shell.text("Save"); primary: true
                      onClicked: { ed.forceActiveFocus()   // commit a number that was just typed first
                                   ed.ta.saveAlarmOf(ed.key, ed.aOn, ed.aVal, ed.bOn, ed.bVal) } }
                Btn { height: 32; width: Math.min(110, (left.width - 16) / 3); compact: true; text: shell.text("Cancel"); onClicked: ed.ta.closeAlarmOf(ed.key) }
                Btn { visible: ed.f.exists === true; height: 32; width: Math.min(130, (left.width - 16) / 3); compact: true; danger: true
                      text: left.width < 400 ? shell.text("Delete") : shell.text("Delete alert"); onClicked: ed.ta.deleteAlarm(ed.key) }
            }
        }
        // ---- right (narrow: below): all prices + history ----
        Column {
            id: rightCol
            visible: !ed.f.list && (ed.f.facts || []).length > 0
            x: ed.wide ? left.x + left.width + 14 : 14
            y: ed.wide ? (ed.stripFull ? left.y : topCol.y) : left.y + left.implicitHeight + 14
            width: ed.wide ? parent.width - x - 14 : parent.width - 28
            spacing: 8
            Head { text: shell.text("ALL PRICES OF THIS PRINTING") }
            // Cardmarket left, TCGplayer right – a small heading per section, fine lines in between
            Row {
                id: ptab
                width: parent.width
                spacing: 24
                readonly property var cols: (ed.f.table || {}).cols || []
                readonly property real colW: (width - spacing * Math.max(0, cols.length - 1)) / Math.max(1, cols.length)
                Repeater {
                    model: ptab.cols
                    Column {
                        id: pc
                        required property var modelData
                        width: ptab.colW
                        spacing: 6
                        Item {   // title = link to the page
                            width: pc.width; height: 24
                            Text { id: pct; anchors.verticalCenter: parent.verticalCenter
                                   text: pc.modelData.title + (pc.modelData.url ? "  ↗" : "")
                                   color: pch.hovered && pc.modelData.url ? T.text : T.text2
                                   font.family: T.font; font.pixelSize: 14; font.bold: true }
                            HoverHandler { id: pch; enabled: !!pc.modelData.url; cursorShape: Qt.PointingHandCursor }
                            TapHandler { enabled: !!pc.modelData.url; gesturePolicy: TapHandler.ReleaseWithinBounds
                                         onTapped: Qt.openUrlExternally(pc.modelData.url) }
                        }
                        Repeater {
                            model: pc.modelData.groups
                            Column {
                                id: pg
                                required property var modelData
                                required property int index
                                width: pc.width
                                spacing: 3
                                Rectangle { width: pg.width; height: 1; color: T.line; opacity: 0.8 }
                                Text { topPadding: 4; text: pg.modelData.title.toUpperCase()
                                       color: T.dim; font.family: T.font; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.1 }
                                Repeater {
                                    model: pg.modelData.rows
                                    Item {
                                        required property var modelData
                                        width: pg.width; height: 20
                                        Text { anchors.verticalCenter: parent.verticalCenter; text: modelData.label
                                               color: T.muted; font.family: T.font; font.pixelSize: 12 }
                                        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                               text: modelData.value; color: T.text; font.family: T.font; font.pixelSize: 12; font.bold: true }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            MarketLinks { width: parent.width; links: ed.f.shops || [] }
            PriceHint {
                visible: !!ed.f.phHint && (ed.f.phHint.text || "") !== ""
                width: parent.width
                hint: ed.f.phHint || ({})
                onLoad: ed.tp.loadPriceHistory()
            }
            PriceChart {
                visible: ed.f.chart !== undefined && (ed.f.chart.lines || []).length > 0
                width: parent.width   // the chart brings its own height (invisible doesn't count in the column)
                info: ed.f.chart || ({})
                onRangePicked: function (days) { ed.ta.setAlarmChartDays(days) }
            }
        }
    }
    }
}
