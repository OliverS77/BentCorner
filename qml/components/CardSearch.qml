// „Search / edit card“: at the top the chosen card (image, name, set, price, foil, languages, back side), then
// Add/Replace · Remove, below that the search (local, Enter/Scryfall) and the hits. cs: qcardsearch.py.
import QtQuick

Item {
    id: root
    property var cs
    property bool closable: cs ? cs.inStream : false
    signal closeRequested()
    readonly property real px: Math.max(12, Math.min(17, width / 24))
    // little height (1280×720): a tighter info field – no rules text, smaller image and keys – so the result list keeps
    // at least three whole rows
    readonly property bool tight: height < 640
    readonly property int ph: tight ? 26 : 30

    Item {
        id: head
        width: root.width; height: root.px * 2.2
        Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - 50; elide: Text.ElideRight
               text: root.cs ? root.cs.title : ""; color: T.text; font.family: T.font; font.pixelSize: root.px + 4; font.bold: true }
        Btn { visible: root.closable; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
              width: 40; height: 32; compact: true; glyph: "close"; onClicked: root.closeRequested() }
    }
    Item {
        id: top
        y: head.height + 6
        width: root.width
        readonly property real pw: Math.max(72, root.width * (root.tight ? 0.17 : 0.24))
        height: Math.max(pw * 88 / 63, infoCol.implicitHeight, camCol.visible ? camCol.implicitHeight : 0)
        Rectangle {
            id: pv
            width: top.pw; height: width * 88 / 63; radius: width * 0.05
            color: Qt.rgba(1, 1, 1, 0.03); border.width: 1; border.color: T.line2
            Image { id: pimg; anchors.fill: parent; anchors.margins: 1; source: root.cs ? root.cs.preview : ""; asynchronous: true
                    fillMode: Image.PreserveAspectFit; smooth: true; mipmap: true; sourceSize.width: 488 }
            // no image (the source has none, or it failed): the crossed-out card, like the row in the hit list
            NoImage { id: noImg; anchors.fill: parent; anchors.margins: 1
                      visible: !!root.cs && root.cs.hasCard && ((root.cs.preview === "" && root.cs.previewText === "")
                                                                || pimg.status === Image.Error
                                                                || (pimg.status === Image.Ready && pimg.implicitWidth < 2)) }
            Text { anchors.centerIn: parent; visible: (!root.cs || root.cs.preview === "") && !noImg.visible; width: parent.width - 12
                   horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                   text: root.cs ? root.cs.previewText : ""; color: T.dim; font.family: T.font; font.pixelSize: root.px - 2 }
            HoverHandler { onHoveredChanged: if (root.cs) { if (hovered) root.cs.hoverPreview(); else root.cs.unhover(-2) } }
        }
        // the scanner's question: the card lying there (camera) on the right, for stamp twins where the stamp sits –
        // beside the info, not below it (the list keeps its rows on small windows)
        Column {
            id: camCol
            visible: !!root.cs && (root.cs.camImage !== "" || root.cs.loupeImage !== "")
            anchors.right: parent.right
            width: Math.round(top.pw * 0.62)
            spacing: 6
            Image { visible: source != ""; source: root.cs ? root.cs.camImage : ""; width: parent.width
                    height: width * 88 / 63; fillMode: Image.PreserveAspectFit; smooth: true }
            Text { visible: !!root.cs && root.cs.camImage !== ""; width: parent.width; horizontalAlignment: Text.AlignHCenter
                   text: shell.text("Camera image"); color: T.dim; font.family: T.font; font.pixelSize: root.px - 4 }
            Image { visible: source != ""; source: root.cs ? root.cs.loupeImage : ""; width: parent.width
                    height: width * 0.66; fillMode: Image.PreserveAspectFit; smooth: true }
            Text { visible: !!root.cs && root.cs.loupeImage !== ""; width: parent.width; wrapMode: Text.Wrap
                   text: shell.text("The stamp sits here"); color: T.dim; font.family: T.font; font.pixelSize: root.px - 4 }
        }
        Column {
            id: infoCol
            x: pv.width + 12; width: root.width - x - (camCol.visible ? camCol.width + 12 : 0)
            spacing: 4
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.cs ? root.cs.name : ""
                   color: T.text; font.family: T.font; font.pixelSize: root.px + 3; font.bold: true }
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.cs ? root.cs.meta : ""
                   color: T.text2; font.family: T.font; font.pixelSize: root.px - 1 }
            // artist · rarity · type line, then the start of the rules text – tells prints apart without hovering
            Text { width: parent.width; wrapMode: Text.Wrap; visible: text !== ""; text: root.cs ? root.cs.details : ""
                   maximumLineCount: root.tight ? 1 : 3; elide: Text.ElideRight   // tight: one line (rows for the list)
                   color: T.text2; font.family: T.font; font.pixelSize: root.px - 2 }
            Text { width: parent.width; wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                   visible: text !== "" && !root.tight; text: root.cs ? root.cs.rules : ""
                   color: T.dim; font.family: T.font; font.pixelSize: root.px - 3 }
            Text { width: parent.width; wrapMode: Text.Wrap; text: root.cs ? root.cs.price : ""; textFormat: Text.RichText
                   color: T.text; font.family: T.font; font.pixelSize: root.px }
            Text { width: parent.width; wrapMode: Text.Wrap; visible: text !== ""; text: root.cs ? root.cs.questionNote : ""
                   color: T.text2; font.family: T.font; font.pixelSize: root.px - 2 }
            // card properties: one labelled row each, with breathing room (finish · condition · language)
            component PropRow: Row {
                property string label
                default property alias content: holder.data
                visible: holder.children.length > 0
                width: infoCol.width; spacing: root.tight ? 0 : 10
                // tight: a narrower label column, so the keys of a row stay on one line
                // (tight: no label at all – the keys say what they are – so a row's keys stay on one line)
                readonly property real labelW: root.tight ? 0 : Math.min(86, infoCol.width * 0.24)
                Text { width: parent.labelW; height: root.ph; verticalAlignment: Text.AlignVCenter; visible: !root.tight
                       text: parent.label; color: T.dim; font.family: T.font; font.pixelSize: root.px - 3; elide: Text.ElideRight }
                Flow { id: holder; width: infoCol.width - parent.labelW - 10; spacing: root.tight ? 6 : 8 }
            }
            Item { width: 1; height: 4 }
            PropRow {
                label: shell.text("Finish")
                visible: root.cs && root.cs.hasCard
                Repeater {
                    model: root.cs ? root.cs.finishOptions : []
                    Btn { required property var modelData
                          height: root.ph; compact: true; checkable: true; text: modelData.text; checked: modelData.on
                          enabled: root.cs && root.cs.finishOptions.length > 1
                          onClicked: root.cs.setFinish(modelData.key) }
                }
                Repeater {   // edition (Pokémon: 1st Edition) – only if it exists for the print
                    model: root.cs ? root.cs.editionOptions : []
                    Btn { required property var modelData
                          height: root.ph; compact: true; checkable: true; text: modelData.text; checked: modelData.on
                          primary: !!root.cs && root.cs.editionHint !== ""   // worth a look: outlined bright
                          // tight: the hint lives here (no line of its own – the list keeps its rows)
                          tip: root.tight && root.cs && root.cs.editionHint !== "" ? root.cs.editionHint
                               : shell.text("On = this copy is that edition (e.g. 1st Edition stamp)")
                          onClicked: root.cs.toggleEdition(modelData.key) }
                }
            }
            Text {   // "1st Edition? Stamp to the left below the picture" – under the finish row (tight: the key's tooltip)
                visible: text !== "" && !root.tight; width: parent.width; wrapMode: Text.Wrap
                text: root.cs ? root.cs.editionHint : ""
                color: T.text2; font.family: T.font; font.pixelSize: root.px - 2
            }
            PropRow {   // (tight: the condition key sits in the language row – one line less)
                label: shell.text("Condition")
                visible: root.cs && root.cs.condText !== "" && !root.tight
                Btn {   // outlined in orange, click = next level
                    height: root.ph; compact: true; text: root.cs ? root.cs.condText : ""
                    alertInk: "#ffb36b"
                    tip: shell.text("Condition – click: next grade (key Z)")
                    onClicked: root.cs.nextCond()
                }
            }
            PropRow {
                label: shell.text("Language")
                visible: root.cs && (root.cs.langs.length > 0 || root.cs.langNote !== "")
                Repeater {
                    model: root.cs ? root.cs.langs : []
                    Btn { required property var modelData
                          required property int index
                          // the language question: the keys are the question – numbered, outlined bright
                          height: root.ph; width: root.cs && root.cs.questionKind === "lang" ? 58 : 46; compact: true
                          text: (root.cs && root.cs.questionKind === "lang" && index < 9 ? (index + 1) + " " : "") + modelData.text
                          primary: !!root.cs && root.cs.questionKind === "lang"
                          tip: modelData.tip
                          enabled: modelData.enabled !== false
                          checkable: true; checked: modelData.on; onClicked: root.cs.pickLang(modelData.code) }
                }
                Text { visible: root.cs && root.cs.langNote !== ""; height: root.ph; verticalAlignment: Text.AlignVCenter
                       text: root.cs ? root.cs.langNote : ""; color: T.dim; font.family: T.font; font.pixelSize: root.px - 3 }
                Btn {   // tight: the condition here, after the languages
                    visible: root.tight && !!root.cs && root.cs.condText !== ""
                    height: root.ph; compact: true; text: root.cs ? root.cs.condText : ""
                    alertInk: "#ffb36b"
                    tip: shell.text("Condition – click: next grade (key Z)")
                    onClicked: root.cs.nextCond()
                }
            }
        }
    }
    Row {
        id: btns
        y: top.y + top.height + 10
        width: root.width
        spacing: 6
        readonly property bool wrongShown: root.cs && root.cs.removeShown && root.cs.inStream
        readonly property real room: root.width - 6 * (wrongShown ? 3 : 2) - 44
        Btn { width: btns.room * (root.cs && root.cs.removeShown ? (btns.wrongShown ? 0.3 : 0.62) : 1); height: root.tight ? 32 : 38
              primary: true; enabled: root.cs ? root.cs.okEnabled : false; text: root.cs ? root.cs.okText : ""
              inverted: !!root.cs && root.cs.editDirty   // changed, not saved yet: bright like "End scan"
              onClicked: root.cs.confirm() }
        Btn { visible: root.cs && root.cs.removeShown; width: btns.room * (btns.wrongShown ? 0.26 : 0.38); height: root.tight ? 32 : 38; danger: true
              text: shell.text("Remove"); tip: shell.text("Remove card from the pack"); onClicked: root.cs.remove() }
        Btn { visible: btns.wrongShown; width: btns.room * 0.44; height: root.tight ? 32 : 38
              text: shell.text("Wrongly recognized")
              tip: shell.text("The card wasn't actually there: remove it and keep it as a scanner mistake (scan data, stays on this computer)")
              onClicked: root.cs.wrongScan() }
        Btn { width: 44; height: 38; text: "⟲"; visible: root.cs && root.cs.backShown; checkable: true
              checked: root.cs ? root.cs.backOn : false; tip: shell.text("Show back side (also in the large preview)")
              onClicked: root.cs.toggleBack() }
    }
    Item {
        id: searchRow
        y: btns.y + btns.height + 10
        width: root.width; height: 36
        SearchField {
            id: sf
            width: parent.width - web.width - 8; height: 36
            placeholder: root.cs ? root.cs.searchHint : shell.text("Search card …")
            text: root.cs ? root.cs.search : ""
            onEdited: function (t) { root.cs.setSearch(t) }
            onAccepted: root.cs.enter()
            // the scanner's question: while the field still holds what it was filled with, 1–9 pick and F switches the
            // finish (then they type; Shift+F types an F); Esc skips right away (not first emptying the field)
            keyHook: function (ev) {
                if (!root.cs || root.cs.questionKind === "")
                    return false
                if (ev.key === Qt.Key_Escape) { root.cs.close(); return true }
                if (sf.text !== root.cs.questionText)
                    return false
                if (ev.key === Qt.Key_F && ev.modifiers === Qt.NoModifier)
                    return root.cs.nextFinish()
                return ev.key >= Qt.Key_1 && ev.key <= Qt.Key_9 && root.cs.pickNumber(ev.key - Qt.Key_0)
            }
            // a question opens: the name filled in is selected – typing replaces it and searches every print
            Connections {
                target: root.cs
                function onChanged() {
                    if (root.cs.questionKind !== "" && root.cs.questionText !== sf.lastQuestion) {
                        sf.lastQuestion = root.cs.questionText
                        Qt.callLater(sf.focusAll)
                    } else if (root.cs.questionKind === "") {
                        sf.lastQuestion = ""
                    }
                }
            }
            property string lastQuestion: ""
            Keys.onUpPressed: root.cs.move(-1)
            Keys.onDownPressed: root.cs.move(1)
        }
        Btn { id: web; anchors.right: parent.right; height: 36; width: 96; compact: true
              text: root.cs && !root.cs.webSearch ? shell.text("All sets") : "Scryfall"
              tip: root.cs && !root.cs.webSearch ? shell.text("Search all sets (including ones not downloaded)")
                                                 : shell.text("Also search Scryfall (sets that are not downloaded)")
              onClicked: root.cs.searchOnline() }
    }
    ListView {
        ScrollHint {}
        id: list
        y: searchRow.y + searchRow.height + 8
        width: root.width; height: root.height - y - infoT.height - 6
        clip: true; boundsBehavior: Flickable.StopAtBounds
        model: root.cs ? root.cs.results : []
        currentIndex: root.cs ? root.cs.current : -1
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, ListView.Contain)
        delegate: Rectangle {
            id: rw
            required property var modelData
            width: list.width; height: Math.round(root.px * 3.1)
            radius: 8
            readonly property bool sel: modelData.i === (root.cs ? root.cs.current : -1)
            color: sel ? T.surface2 : (rh.hovered ? Qt.lighter(T.surface, 1.15) : "transparent")
            border.width: sel ? 1 : 0; border.color: T.line2
            Image { id: th; x: 6; anchors.verticalCenter: parent.verticalCenter; height: parent.height - 8; width: height * 63 / 88
                    source: rw.modelData.img; asynchronous: true; fillMode: Image.PreserveAspectFit; sourceSize.height: 140 }
            Rectangle {   // still loading: a quiet empty frame (never the crossed-out card for that)
                anchors.fill: th; radius: 3; color: "transparent"; border.width: 1; border.color: T.line
                visible: th.status === Image.Loading
            }
            NoImage { anchors.fill: th; thumb: true   // none, failed, or an empty answer (the source has no image)
                      visible: (rw.modelData.img || "") === "" || th.status === Image.Error
                               || (th.status === Image.Ready && th.implicitWidth < 2) }
            Column {
                x: th.x + th.width + 10; anchors.verticalCenter: parent.verticalCenter; width: parent.width - x - (rw.modelData.back ? 44 : 10)
                Text { width: parent.width; elide: Text.ElideRight; text: rw.modelData.name; color: T.text
                       font.family: T.font; font.pixelSize: root.px; font.bold: rw.sel }
                Text { width: parent.width; elide: Text.ElideRight; text: rw.modelData.sub; color: T.muted
                       font.family: T.font; font.pixelSize: root.px - 2 }
            }
            HoverHandler { id: rh; cursorShape: Qt.PointingHandCursor
                           onHoveredChanged: if (hovered) root.cs.hover(rw.modelData.i); else root.cs.unhover(rw.modelData.i) }
            TapHandler {
                onTapped: function (ev, b) { if (tapCount === 1) root.cs.select(rw.modelData.i) }
                onDoubleTapped: root.cs.pick(rw.modelData.i)
            }
            Btn { visible: rw.modelData.back; anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                  width: 32; height: 28; compact: true; text: "⟲"; tip: shell.text("Show back side (also in the large preview)")
                  onClicked: root.cs.toggleRowBack(rw.modelData.i) }
        }
    }
    Text { id: infoT; y: root.height - height; width: root.width; wrapMode: Text.Wrap
           text: root.cs ? root.cs.info : ""; color: T.muted; font.family: T.font; font.pixelSize: root.px - 2 }
    // focus only while visible – hidden, the field would swallow the scan page's shortcuts
    Component.onCompleted: if (visible) sf.focusAll()
    onVisibleChanged: visible ? sf.focusAll() : sf.dropFocus()
}
