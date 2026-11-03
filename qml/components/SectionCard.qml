// One section of the advanced search (header: checkmark on/off or title, „Reset“; content depending on kind).
import QtQuick

Rectangle {
    id: card
    property var sec: ({})
    property var adv
    radius: Math.min(12, T.panelRadius)
    color: T.surface
    border.width: 1; border.color: T.line

    // header
    Item {
        id: head
        TextMetrics { id: resetM; font.family: T.font; font.pixelSize: 13; text: shell.text("Reset") }
        x: 12; y: 8
        width: card.width - 24; height: 26
        CheckBox {
            id: headCheck
            visible: card.sec.toggle
            anchors.verticalCenter: parent.verticalCenter
            text: card.sec.title
            checked: card.sec.checked
            tip: shell.text("Section on/off – the selection inside is kept")
            onToggled: function (on) { card.adv.toggleSection(card.sec.key, on) }
        }
        Text {
            id: headTitle
            visible: !card.sec.toggle
            anchors.verticalCenter: parent.verticalCenter
            text: card.sec.title
            color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true
        }
        Btn {
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            compact: true; danger: true; height: 24
            // no room next to the title (e.g. "Sets"): only ↺ – "Zurücksetzen" covered it (Oliver's test of 0.9.2)
            text: (card.sec.toggle ? headCheck.implicitWidth : headTitle.implicitWidth) + resetM.width + 34 > head.width
                  ? "↺" : shell.text("Reset")
            tip: shell.text("Reset section")
            onClicked: card.adv.resetSection(card.sec.key)
        }
    }
    Loader {
        id: body
        x: 12; y: head.y + head.height + 8
        width: card.width - 24
        height: card.height - y - 10
        opacity: card.sec.active ? 1 : 0.55
        Behavior on opacity { NumberAnimation { duration: 160 } }
        enabled: card.sec.enabled !== false
        sourceComponent: card.sec.kind === "tri" ? cTri : card.sec.kind === "list" ? cList : card.sec.kind === "sets" ? cSets
                       : card.sec.kind === "colors" ? cColors : card.sec.kind === "opts" ? cOpts : card.sec.kind === "range" ? cRange
                       : card.sec.kind === "count" ? cCount : card.sec.kind === "text" ? cText : null
    }

    readonly property var modeItems: [{key: "any", text: shell.text("at least one of them")}, {key: "all", text: shell.text("all at once")}]

    // ---------- Triple checkmarks (types, supertype, rarity, legal in) ----------
    Component {
        id: cTri
        Item {
            Flickable {
                ScrollHint {}
                anchors.fill: parent; anchors.bottomMargin: card.sec.mode ? 34 : 0
                contentHeight: grid.height; clip: true; boundsBehavior: Flickable.StopAtBounds
                Grid {
                    id: grid
                    width: parent.width
                    columns: card.sec.columns || 1
                    columnSpacing: 4; rowSpacing: 1
                    Repeater {
                        model: card.sec.items
                        TriItem {
                            required property var modelData
                            width: (grid.width - 4 * (grid.columns - 1)) / grid.columns
                            text: modelData.label; state: modelData.state; binary: card.sec.binary
                            onClicked: card.adv.triClick(card.sec.key, modelData.value)
                            onSolo: card.adv.triSolo(card.sec.key, modelData.value)
                        }
                    }
                }
            }
            Seg {   // two choices: chips in place (selection = brightness)
                visible: !!card.sec.mode
                anchors.bottom: parent.bottom
                items: card.modeItems; current: card.sec.mode || "any"
                onPicked: function (k) { card.adv.setMode(card.sec.key, k) }
            }
        }
    }

    // ---------- Long list (subtype, keywords) ----------
    Component {
        id: cList
        Item {
            SearchField {
                id: lf
                width: parent.width; height: 32; z: 5
                placeholder: card.sec.placeholder
                onEdited: function (t) { sug.items = card.adv.listSuggest(card.sec.key, t) }
                onAccepted: { card.adv.listEnter(card.sec.key, text); text = ""; sug.items = [] }
            }
            SuggestList {
                id: sug
                parent: lf.Window.window ? lf.Window.window.contentItem : lf   // above everything (like the sets)
                z: 1000
                property point at: Qt.point(0, lf.height + 2)
                x: at.x; y: at.y
                onItemsChanged: if (parent) at = lf.mapToItem(parent, 0, lf.height + 2)
                visible: height > 0 && lf.visible
                width: lf.width
                onPicked: function (it) { card.adv.listAdd(card.sec.key, it.name, lf.text.trim().indexOf("-") === 0); lf.text = ""; items = [] }
            }
            Flickable {
                ScrollHint {}
                y: lf.height + 8
                width: parent.width; height: parent.height - y - 38
                contentHeight: tags.height; clip: true; boundsBehavior: Flickable.StopAtBounds
                Flow {
                    id: tags
                    width: parent.width; spacing: 5
                    Text { visible: card.sec.tags.length === 0; text: shell.text("nothing selected yet"); color: T.dim
                           font.family: T.font; font.pixelSize: 12 }
                    Repeater {
                        model: card.sec.tags
                        StateTag {
                            required property var modelData
                            name: modelData.name; state: modelData.state
                            onToggled: card.adv.listToggle(card.sec.key, modelData.name)
                            onRemoved: card.adv.listRemove(card.sec.key, modelData.name)
                        }
                    }
                }
            }
            Seg {
                anchors.bottom: parent.bottom
                items: card.modeItems; current: card.sec.mode
                onPicked: function (k) { card.adv.setMode(card.sec.key, k) }
            }
        }
    }

    // ---------- Sets ----------
    Component {
        id: cSets
        Column {
            spacing: 8
            SearchField {
                id: sf
                width: parent.width; height: 32; z: 5
                placeholder: shell.text("+ Search set (name or code) …")
                onEdited: function (t) { ssug.items = card.adv.setSuggest(t) }
                onAccepted: { card.adv.setEnter(text); text = ""; ssug.items = [] }
                SuggestList {
                    id: ssug
                    // above everything (Oliver's test of 0.9.2: it lay behind Colors and Card type): the window's
                    // top layer, placed under the field when it fills
                    parent: sf.Window.window ? sf.Window.window.contentItem : sf
                    z: 1000
                    property point at: Qt.point(0, sf.height + 2)
                    x: at.x; y: at.y
                    onItemsChanged: if (parent) at = sf.mapToItem(parent, 0, sf.height + 2)
                    visible: height > 0 && sf.visible
                    width: Math.max(sf.width, 460)
                    sets: true
                    onPicked: function (it) { card.adv.setAdd(it.codes); sf.text = ""; items = [] }
                }
            }
            Seg {   // narrow section (e.g. Lorcana at 1600 px): short keys, the full text as tooltip
                enabled: card.sec.modeEnabled
                readonly property bool narrow: card.width < 380
                items: narrow ? [{key: "or", text: shell.text("OR"), tip: shell.text("OR – in one of them")},
                                 {key: "and", text: shell.text("AND"), tip: shell.text("AND – in all of them")}]
                              : [{key: "or", text: shell.text("OR – in one of them")}, {key: "and", text: shell.text("AND – in all of them")}]
                current: card.sec.mode
                onPicked: function (k) { card.adv.setMode("sets", k) }
            }
            Flow {
                width: parent.width; spacing: 5
                Repeater {
                    model: card.sec.codes
                    StateTag { required property var modelData; name: modelData; state: 1; toggleable: false
                               onRemoved: card.adv.setRemove(modelData) }
                }
            }
        }
    }

    // ---------- Colours ----------
    Component {
        id: cColors
        Column {
            spacing: 10
            Row {
                spacing: 6
                Repeater {
                    model: card.sec.colors
                    Rectangle {
                        required property var modelData
                        readonly property bool on: card.sec.selected.indexOf(modelData.code) >= 0
                        width: 28; height: 28; radius: 14
                        color: on ? modelData.hex : "transparent"
                        border.width: 2; border.color: modelData.hex
                        scale: ch.hovered ? 1.08 : 1
                        Behavior on scale { NumberAnimation { duration: 120 } }
                        Behavior on color { ColorAnimation { duration: 140 } }
                        Text { anchors.centerIn: parent; text: modelData.code; color: parent.on ? T.onHi : T.text
                               font.family: T.font; font.pixelSize: 12; font.bold: true }
                        HoverHandler { id: ch; cursorShape: Qt.PointingHandCursor
                            onHoveredChanged: {
                                if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 4); shell.tip(modelData.tip, p.x, p.y) }
                                else shell.tip("", 0, 0)
                            } }
                        TapHandler {
                            id: ct
                            onTapped: card.adv.colorClick(modelData.code)   // Python spots double clicks (see TriItem)
                        }
                    }
                }
            }
            Seg {
                items: [{key: "any", text: shell.text("includes")}, {key: "exact", text: shell.text("exactly")}, {key: "atmost", text: shell.text("at most")}]
                current: card.sec.mode
                onPicked: function (k) { card.adv.setMode("colors", k) }
            }
            Text { width: parent.width; wrapMode: Text.Wrap; color: T.dim; font.family: T.font; font.pixelSize: 11
                   text: card.sec.specials ? shell.text("C = colorless · M = multicolored. Double-click a color = exactly this one, again = without this color (all others and colorless)")
                                           : card.sec.hint }
        }
    }

    // ---------- Display / deck ----------
    Component {
        id: cOpts
        Flickable {
            ScrollHint {}
            contentHeight: oc.height; clip: true; boundsBehavior: Flickable.StopAtBounds
            Column {
                id: oc
                width: parent.width; spacing: 8
                Text { visible: card.sec.langsVisible === true; text: shell.text("only cards in …"); color: T.muted
                       font.family: T.font; font.pixelSize: 12 }
                Flow {
                    visible: card.sec.langsVisible === true
                    width: parent.width; spacing: 4
                    Repeater {
                        model: card.sec.langs || []
                        Rectangle {
                            required property var modelData
                            width: lt.implicitWidth + 14; height: 24; radius: 10
                            color: modelData.sel ? "#d9dce6" : "transparent"
                            border.width: 1; border.color: modelData.sel ? "#d9dce6" : (modelData.present ? T.line2 : T.line)
                            Text { id: lt; anchors.centerIn: parent; text: modelData.short
                                   color: modelData.sel ? T.onHi : (modelData.present ? T.text2 : T.dim)
                                   font.family: T.font; font.pixelSize: 12; font.bold: true }
                            HoverHandler { cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: card.adv.langToggle(modelData.code) }
                        }
                    }
                }
                Seg {
                    visible: card.sec.langsVisible === true
                    items: [{key: "or", text: shell.text("OR")}, {key: "and", text: shell.text("AND")}]
                    current: card.sec.langMode || "or"
                    onPicked: function (k) { card.adv.setLangMode(k) }
                }
                Flow {   // narrow: the keys move below "Foil" instead of being cut off at the edge
                    visible: card.sec.foilVisible === true
                    width: parent.width
                    spacing: 8
                    Text { height: 28; verticalAlignment: Text.AlignVCenter; text: shell.text("Foil"); color: T.muted
                           font.family: T.font; font.pixelSize: 12 }
                    Seg {
                        items: [{key: "any", text: shell.text("any")}, {key: "only", text: shell.text("only")}, {key: "none", text: shell.text("kein")}]
                        current: card.sec.foil || "any"
                        onPicked: function (k) { card.adv.setFoil(k) }
                    }
                }
                Repeater {
                    model: card.sec.checks || []
                    CheckBox { required property var modelData; width: oc.width; text: modelData.text; checked: modelData.on
                               tip: modelData.tip; onToggled: function (on) { card.adv.setCheck(modelData.name, on) } }
                }
            }
        }
    }

    // ---------- Values ----------
    Component {
        id: cRange
        Column {
            spacing: 6
            Repeater {
                model: card.sec.rows
                Row {
                    required property var modelData
                    spacing: 6
                    Text { width: 84; anchors.verticalCenter: parent.verticalCenter; text: modelData.label; color: T.text2
                           font.family: T.font; font.pixelSize: 12; elide: Text.ElideRight }
                    RangeField { width: (card.width - 24 - 84 - 12) / 2; value: modelData.lo; decimals: modelData.dec
                                 onCommitted: function (v) { card.adv.rangeSet(modelData.key, 0, v) } }
                    RangeField { width: (card.width - 24 - 84 - 12) / 2; value: modelData.hi; decimals: modelData.dec
                                 onCommitted: function (v) { card.adv.rangeSet(modelData.key, 1, v) } }
                }
            }
        }
    }

    // ---------- Ownership ----------
    Component {
        id: cCount
        Column {
            spacing: 6
            StepSlider {
                width: Math.min(parent.width, 240)
                from: 1; to: card.sec.labels.length; value: card.sec.n; showNumber: false
                onMoved: function (v) { card.adv.countSet(v) }
            }
            Row {
                spacing: 0
                Repeater { model: card.sec.labels
                    Text { required property var modelData; required property int index
                           width: Math.min(card.width - 24, 240) / card.sec.labels.length; horizontalAlignment: Text.AlignHCenter
                           text: modelData; color: index + 1 === card.sec.n ? T.text : T.dim; font.family: T.font; font.pixelSize: 11 } }
            }
            Seg {
                items: [{key: "min", text: shell.text("at least")}, {key: "exact", text: shell.text("exactly")}]
                current: card.sec.mode
                onPicked: function (k) { card.adv.setMode("count", k) }
            }
        }
    }

    // ---------- Text contains ----------
    Component {
        id: cText
        Column {
            spacing: 6
            property string field: "oracle"
            DropList { width: parent.width; height: 30; items: card.sec.fields; current: parent.field
                       onPicked: function (k) { parent.field = k } }
            SearchField { id: tf; width: parent.width; height: 30; placeholder: shell.text("Phrase, e.g. draw a card")
                          onAccepted: { card.adv.textAdd(parent.field, text, neg.checked); text = "" } }
            CheckBox { id: neg; text: shell.text("does NOT contain") }
            Btn { width: parent.width; height: 30; text: shell.text("+ Add")
                  onClicked: { card.adv.textAdd(parent.field, tf.text, neg.checked); tf.text = "" } }
            Text { width: parent.width; wrapMode: Text.Wrap; color: T.dim; font.family: T.font; font.pixelSize: 11
                   text: shell.text("Each phrase becomes a chip. Several phrases must all match.") }
        }
    }
}
