// Deck editor: header row (name, format, summary, save …), the same search as in the Library, below it
// three areas – deck list/deck info, cards (search results or upgrades), detail (+ comparison) with the
// deck buttons. Fixed order, widths via grips in between; „Lists“ splits the left column (grip in the
// middle). Logic: de (qdeckedit.py).
import QtQuick
import "."

Item {
    id: root
    property var de
    onVisibleChanged: de.setActive(visible)
    Component.onCompleted: de.setActive(visible)

    // ================= Header row =================
    Item {
        id: head
        x: 20; y: 12
        width: root.width - 40; height: 40
        Btn { id: backB; height: 38; width: 150; backDir: -1; text: shell.text("All decks"); onClicked: de.back() }
        Item {
            id: nameBox
            x: backB.width + 12; height: 38; z: 30
            width: Math.max(200, head.width - x - rightRow.width - 12)
            RenameField {   // click on the name = rename, like everywhere (review .101)
                x: 6; anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, parent.width - 12); height: 30
                text: de.name; pixelSize: 20; bold: true
                commit: function (v) { de.setName(v); return true }
            }
        }
        Row {
            id: rightRow
            anchors.right: parent.right
            spacing: 8
            DropList { height: 38; width: 150; items: de.formats; current: de.format; onPicked: function (k) { de.setFormat(k) } }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: de.summary; textFormat: Text.RichText
                color: T.text; font.family: T.font; font.pixelSize: 13
                HoverHandler { id: sumH
                    onHoveredChanged: if (hovered && de.summaryTip) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(de.summaryTip, p.x, p.y) } else shell.tip("", 0, 0) }
            }
            Text { anchors.verticalCenter: parent.verticalCenter; visible: de.dirty; text: shell.text("● unsaved")
                   color: "#d9b46a"; font.family: T.font; font.pixelSize: 13; font.bold: true }
            Btn { height: 38; visible: de.dirty; danger: true; text: shell.text("Discard")
                  tip: shell.text("Undo all changes since the last save"); onClicked: de.discard() }
            Btn { height: 38; text: shell.text("Save"); enabled: de.dirty; active: de.dirty
                  tip: shell.text("Save the deck changes (Ctrl+S)"); onClicked: de.save() }
            Btn { height: 38; text: shell.text("Export") + "  ▾"; onClicked: de.exportMenu() }
            Btn { height: 38; text: shell.text("Built"); checkable: true; checked: de.built
                  tip: shell.text("I really built this deck – its cards are in use: they no longer count as free for suggestions, upgrades and other decks")
                  onClicked: de.toggleBuilt() }
            Btn { height: 38; text: shell.text("Versions ▾")
                  tip: shell.text("Save as a new version, compare with another deck, put into a folder")
                  onClicked: de.versionsMenu() }
            Btn { height: 38; danger: true; text: shell.text("Delete"); onClicked: de.deleteDeck() }
        }
    }

    // ================= Search =================
    Item {
        id: search
        x: 20; y: head.y + head.height + 10
        width: root.width - 40; height: 36
        Row {
            id: modes
            spacing: 8
            Btn { height: 36; width: Math.max(160, implicitWidth); text: shell.text("My collection"); checkable: true; checked: de.mode === "mine"
                  tip: shell.text("Only cards you own (in your printing)"); onClicked: de.setMode("mine") }
            Btn { height: 36; width: Math.max(120, implicitWidth); text: shell.text("All cards"); checkable: true; checked: de.mode === "all"
                  tip: shell.text("All cards from the card database"); onClicked: de.setMode("all") }
            Btn { height: 36; width: Math.max(110, implicitWidth); navIcon: "lists"; text: shell.text("Lists"); visible: de.listsLib !== null
                  checkable: true; checked: root.listsOpen
                  tip: shell.text("Show lists below the deck list – drag cards from the deck list onto them")
                  onClicked: root.listsOpen = !root.listsOpen }
        }
        SearchField {
            id: sfield
            anchors.left: modes.right; anchors.leftMargin: 10
            anchors.right: sRight.left; anchors.rightMargin: 10
            height: 36
            placeholder: de.placeholder
            text: de.searchText
            onEdited: function (t) { de.setSearch(t); acList.query(t) }
            onAccepted: { if (acList.cur >= 0 && acList.visible) acList.pick(acList.cur); else { acList.close(); de.commitSearch() } }
            onUpPressed: acList.step(-1)
            onDownPressed: acList.step(1)
            onInputFocusChanged: if (!inputFocus) acTimer.stop(), acList.close()
        }
        Row {
            id: sRight
            anchors.right: parent.right
            spacing: 10
            Btn { height: 36; text: de.adv.buttonText + (de.adv.open ? "  ▴" : "  ▾"); active: de.adv.open
                  onClicked: de.adv.setOpen(!de.adv.open) }
            DropList { height: 36; width: 250; items: de.sorts; current: de.sort; onPicked: function (k) { de.setSort(k) }
                       directional: true; reversed: de.sortReversed; onReverse: de.toggleSortDir() }
            Rectangle {
                height: 36; width: slider.width + 46
                radius: 10; color: "transparent"; border.width: 1; border.color: T.line2
                Canvas {
                    onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up first paint
                    x: 12; anchors.verticalCenter: parent.verticalCenter; width: 16; height: 16
                    onPaint: { var g = getContext("2d"); g.reset(); g.strokeStyle = T.text2; g.lineWidth = 1.6
                        g.beginPath(); g.moveTo(5.5, 1); g.lineTo(5.5, 15); g.moveTo(10.5, 1); g.lineTo(10.5, 15)
                        g.moveTo(1, 5.5); g.lineTo(15, 5.5); g.moveTo(1, 10.5); g.lineTo(15, 10.5); g.stroke() }
                }
                StepSlider { id: slider; x: 34; anchors.verticalCenter: parent.verticalCenter; width: 160
                             // upgrades: always pairs (2 columns) – slider shows 2 and is disabled
                             enabled: !de.upgradeView; opacity: de.upgradeView ? 0.45 : 1
                             from: de.upgradeView ? Math.min(2, de.colMin) : de.colMin; to: from + 5
                             value: de.upgradeView ? 2 : de.columns
                             onMoved: function (v) { de.setColumns(v) } }
            }
        }
    }
    // autocomplete: card names below the search field (in the window, no pop-up) – click/Enter = show card
    Timer { id: acTimer; interval: 140; onTriggered: acList.items = de.suggestNames(acList.text) }
    Rectangle {
        id: acList
        z: 40
        property var items: []
        property string text: ""
        property int cur: -1
        function query(t) { text = t; cur = -1; acTimer.restart() }
        function close() { items = []; cur = -1 }
        function step(d) { if (items.length) cur = Math.max(0, Math.min(items.length - 1, cur + d)) }
        function pick(i) { if (i >= 0 && i < items.length) { var n = items[i].name; close(); de.pickName(n) } }
        visible: items.length > 0 && sfield.inputFocus
        x: search.x + sfield.x; y: search.y + search.height + 4
        width: Math.max(320, sfield.width * 0.6); height: acCol.implicitHeight + 8
        radius: 10; color: T.surface; border.width: 1; border.color: T.line2
        Column {
            id: acCol
            x: 4; y: 4; width: parent.width - 8
            Repeater {
                model: acList.items
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    width: acCol.width; height: 30; radius: 7
                    color: (acList.cur === index || ach.hovered) ? T.surface2 : "transparent"
                    Text { x: 10; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 60; elide: Text.ElideRight
                           text: modelData.name; color: T.text; font.family: T.font; font.pixelSize: 14 }
                    Text { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
                           visible: modelData.owned; text: "✓"; color: T.text2; font.family: T.font; font.pixelSize: 13
                           font.bold: true }
                    HoverHandler { id: ach; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: acList.pick(index) }
                }
            }
        }
    }
    AdvSearch {
        id: advPanel
        z: 15
        x: 20; width: root.width - 40
        anchors.top: search.bottom; anchors.topMargin: 10
        adv: de.adv
    }
    ChipBar {
        id: chips
        x: 20; width: root.width - 40
        anchors.top: advPanel.bottom; anchors.topMargin: de.chips.length ? 8 : 0
        groups: de.chips
        onChipClicked: function (id) { de.chip(id) }
    }
    // alternatives: which kinds?
    Flow {
        id: altBar
        x: 20; width: root.width - 40
        anchors.top: chips.bottom; anchors.topMargin: de.altOpen ? 8 : 0
        height: de.altOpen ? implicitHeight : 0
        visible: de.altOpen
        spacing: 8
        // from where: from your collection / don't have / all cards
        Row {
            spacing: 0
            Repeater {
                model: de.altOwnedOptions
                delegate: Rectangle {
                    required property var modelData
                    required property int index
                    readonly property bool on: de.altOwned === modelData.key
                    height: 30; width: aot.implicitWidth + 26
                    radius: 15
                    color: on ? "#d9d9d9" : (aoh.hovered ? T.surface2 : T.surface)
                    border.width: 1; border.color: on ? "#d9d9d9" : T.line2
                    Text { id: aot; anchors.centerIn: parent; text: modelData.text; color: parent.on ? T.onHi : T.text2
                           font.family: T.font; font.pixelSize: 13; font.bold: true }
                    HoverHandler { id: aoh; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: de.setAltOwned(modelData.key) }
                }
            }
        }
        Item { width: 6; height: 30 }
        Text { height: 30; verticalAlignment: Text.AlignVCenter; text: de.altLabel; textFormat: Text.StyledText
               color: T.muted; font.family: T.font; font.pixelSize: 13 }
        Repeater {
            model: de.altKinds
            delegate: Rectangle {
                required property var modelData
                height: 30; radius: 15; width: akt.implicitWidth + 28
                color: modelData.on ? "#d9d9d9" : (akh.hovered ? T.surface2 : T.surface)
                border.width: 1; border.color: modelData.on ? "#d9d9d9" : T.line2
                Text { id: akt; anchors.centerIn: parent; text: modelData.text; color: modelData.on ? T.onHi : T.text2
                       font.family: T.font; font.pixelSize: 13; font.bold: true }
                HoverHandler { id: akh; cursorShape: Qt.PointingHandCursor
                    onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(modelData.tip, p.x, p.y) } else shell.tip("", 0, 0) }
                TapHandler { onTapped: de.toggleAltKind(modelData.key) }
            }
        }
    }

    // ================= Three areas =================
    Item {
        id: area
        x: 20; width: root.width - 40
        anchors.top: altBar.bottom; anchors.topMargin: 12
        anchors.bottom: parent.bottom; anchors.bottomMargin: 12
        readonly property var order: ["list", "cards", "detail"]
        property var frac: de.split
        property real dragFrac: -1
        readonly property real gap: 14
        readonly property real gapL: 26   // more room to the left of the grip
        readonly property bool detOn: de.detailOpen
        // widths: detail closed = cards get the space
        readonly property real avail: width - gapL - gap
        readonly property real fl: frac.list
        readonly property real fd: detOn ? frac.detail : 0
        readonly property real fc: frac.cards + (detOn ? 0 : frac.detail)
        property real wList: listW()
        property real wDetail: detailW()
        function listW() { return Math.max(360, avail * fl / (fl + fd + fc)) }
        function detailW() { return detOn ? Math.max(de.compareOpen ? 660 : 340, avail * fd / (fl + fd + fc)) : 0 }
        function rebind() { wList = Qt.binding(listW); wDetail = Qt.binding(detailW) }
        readonly property real wCards: Math.max(330, avail - wList - wDetail)
        Behavior on wDetail { enabled: shell.animate && !area.divDrag.active; NumberAnimation { duration: 300 * shell.speed; easing.type: Easing.InOutCubic } }
        function widthOf(k) { return k === "list" ? wList : (k === "detail" ? wDetail : wCards) }
        function xOf(k) {
            if (k === "list") return 0
            if (k === "cards") return wList + gapL
            return wList + gapL + wCards + gap
        }
        function panel(k) { return k === "list" ? listPanel : (k === "detail" ? detailPanel : cardsPanel) }
        property var divDrag: QtObject { property bool active: false }

        // ---- Grips in between: widths ----
        Repeater {
            model: 2
            delegate: Item {
                id: dv
                required property int index
                readonly property string leftKey: area.order[index]
                readonly property string rightKey: area.order[index + 1]
                visible: area.widthOf(leftKey) > 1 && area.widthOf(rightKey) > 1
                // left: centred between deck list and card (the cards have 8 px padding)
                x: index === 0 ? area.wList + (area.gapL + 8) / 2 - 5 : area.xOf(rightKey) - area.gap / 2 - 5
                width: 10; height: area.height
                z: 20
                Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5; color: dh.hovered || dd.active ? T.text2 : T.line2 }
                HoverHandler { id: dh; cursorShape: Qt.SplitHCursor }
                DragHandler {
                    id: dd
                    target: null; yAxis.enabled: false
                    property real sl: 0
                    property real sr: 0
                    onActiveChanged: {
                        area.divDrag.active = active
                        if (active) { sl = area.widthOf(dv.leftKey); sr = area.widthOf(dv.rightKey) }
                        else {
                            var f = {}
                            var tot = area.wList + area.wCards + area.wDetail
                            f.list = area.wList / tot; f.cards = area.wCards / tot
                            f.detail = area.detOn ? area.wDetail / tot : area.frac.detail
                            de.setSplit(f)
                            area.rebind()
                        }
                    }
                    onTranslationChanged: {
                        if (!active) return
                        var dx = translation.x
                        // the cards take the rest; the list or detail is what gets dragged
                        if (dv.leftKey === "list") area.wList = Math.max(360, sl + dx)
                        else if (dv.rightKey === "list") area.wList = Math.max(360, sr - dx)
                        if (dv.leftKey === "detail" && area.detOn) area.wDetail = Math.max(340, sl + dx)
                        else if (dv.rightKey === "detail" && area.detOn) area.wDetail = Math.max(340, sr - dx)
                    }
                }
            }
        }

        // ================= Cards =================
        Item {
            id: cardsPanel
            x: area.xOf("cards"); width: area.wCards; height: area.height
            Item {
                id: hintRow
                y: 14; width: parent.width; height: 30
                Text { anchors.verticalCenter: parent.verticalCenter; width: parent.width - (de.subset ? 190 : 0)
                       text: de.hint; textFormat: Text.StyledText; elide: Text.ElideRight
                       color: T.muted; font.family: T.font; font.pixelSize: 13 }
                Btn { visible: de.subset; anchors.right: parent.right; height: 30; compact: true
                      text: shell.text("✕  back to search"); onClicked: de.backToSearch() }
            }
            Rectangle {   // row from the deck list is dragged here: out of the deck
                anchors.fill: results; anchors.margins: -4
                visible: ghost.visible && ghost.kind === "row" && ghost.over(cardsPanel)
                radius: 12; color: Qt.rgba(1, 1, 1, 0.04); border.width: 2; border.color: T.text2
            }
            GridView {
                EdgeFade {}
                ScrollHint {}
                id: results
                y: hintRow.y + hintRow.height + 6
                width: parent.width; height: parent.height - y - tipT.height - 6
                visible: !de.upgradeView
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                flickDeceleration: 3500
                model: de.results
                cacheBuffer: Math.round(Math.max(2, Math.min(8, 60 / Math.max(1, cols))) * cellHeight)   // ~60 cards each way
                readonly property int cols: Math.max(1, de.columns)
                cellWidth: Math.floor((width - 10) / cols)
                readonly property real cw: cellWidth - 16
                cellHeight: Math.round(cw * 88 / 63) + 36
                delegate: Item {
                    id: rt
                    required property var modelData
                    width: results.cellWidth; height: results.cellHeight
                    CardTile {
                        id: tile
                        anchors.fill: parent
                        name: ""
                        price: ""
                        setLine: ""
                        chips: rt.modelData.chips
                        decks: rt.modelData.decks || []
                        img: rt.modelData.img
                        draggable: true
                        onClicked: de.showResult(rt.modelData.i)
                        onDoubleClicked: de.addResult(rt.modelData.i)
                        onDragMoved: function (sx, sy) { ghost.move("result", rt.modelData.i, "+ " + rt.modelData.name, sx, sy) }
                        onDragEnded: function (sx, sy) { ghost.drop(sx, sy) }
                    }
                    Text { anchors.horizontalCenter: parent.horizontalCenter; y: 8 + tile.ch + 6
                           text: rt.modelData.price; color: T.muted; font.family: T.font; font.pixelSize: 12 }
                    HoverHandler { id: rth
                        onHoveredChanged: if (rt.modelData.why) { if (hovered) { var p = rt.mapToItem(null, rt.width / 2, rt.height * 0.6); shell.tip("<b>" + rt.modelData.name + "</b><br>" + rt.modelData.why.replace(/\n/g, "<br>"), p.x, p.y) } else shell.tip("", 0, 0) } }
                    // buttons on hover: − left (only if in the deck), + and ⋮ on the right
                    Row {
                        visible: rth.hovered
                        x: 8 + tile.cw - width - 8; y: 8 + tile.ch - height - 8
                        spacing: 0
                        Btn { width: 34; height: 32; compact: true; text: "+"; fontPx: 18; tip: shell.text("To deck"); onClicked: de.addResult(rt.modelData.i) }
                        Btn { width: 28; height: 32; compact: true; text: "⋮"; fontPx: 16; tip: shell.text("More: commander, sideboard, maybeboard, this exact print")
                              onClicked: de.resultMenu(rt.modelData.i) }
                    }
                    Btn {
                        visible: rth.hovered && rt.modelData.inDeck > 0
                        x: 16; y: 8 + tile.ch - height - 8
                        width: 34; height: 32; compact: true; text: "−"; fontPx: 18; tip: shell.text("One less in the deck")
                        onClicked: de.removeResult(rt.modelData.i)
                    }
                }
            }
            Loader {
                id: upView
                y: results.y; width: parent.width; height: results.height
                active: de.upgradeView
                visible: active
                source: "../UpgradeList.qml"
                onLoaded: { item.upModel = de.upModel; item.upTexts = de.upTexts; item.upBridge = Qt.binding(function () { return de.upBridge }); item.current = Qt.binding(function () { return de.upCurrent }) }
            }
            Text {
                id: tipT
                y: parent.height - height
                text: ""   // (usage hints removed – they explain themselves on the first click)
                visible: false
                color: T.dim; font.family: T.font; font.pixelSize: 12
            }
        }

        // ================= Detail (+ comparison) =================
        Item {
            id: detailPanel
            x: area.xOf("detail"); width: area.wDetail; height: area.height
            visible: width > 1
            clip: true
            readonly property real half: de.compareOpen ? (width - 14) / 2 : width
            component Acts: Column {
                property var a
                property string which
                spacing: 6
                visible: !!(a && a.shown)
                Text { text: parent.a && parent.a.label ? parent.a.label : ""; textFormat: Text.StyledText
                       color: T.text; font.family: T.font; font.pixelSize: 14 }
                Flow {
                    width: parent.width; spacing: 8
                    Btn { height: 34; primary: true; text: shell.text("+ Add to deck"); onClicked: de.act(parent.parent.which, "add") }
                    Btn { height: 34; visible: !!(parent.parent.a && parent.parent.a.cmdr); text: shell.text("As commander"); onClicked: de.act(parent.parent.which, "cmdr") }
                    Btn { height: 34; text: shell.text("Sideboard"); onClicked: de.act(parent.parent.which, "side") }
                    Btn { height: 34; visible: !!(parent.parent.a && parent.parent.a.print); text: shell.text("Use this printing")
                          tip: shell.text("The deck contains another printing of this card – switch to this one")
                          onClicked: de.act(parent.parent.which, "print") }
                    Btn { height: 34; navIcon: "swap"; text: shell.text("Alternatives"); checkable: true; checked: !!(parent.parent.a && parent.parent.a.alt)
                          tip: shell.text("Alternatives: cards that could replace this one – stronger, cheaper, same job …")
                          onClicked: de.act(parent.parent.which, "alt") }
                    Btn { height: 34; text: shell.text("More …"); tip: shell.text("One less, maybeboard, move, remove from deck")
                          onClicked: de.act(parent.parent.which, "more") }
                }
                Item {
                    visible: !!(parent.a && parent.a.inUse); width: parent.width; height: aiT.implicitHeight
                    NavIcon { key: "flag"; s: 0.7; color: T.text2; y: -1 }
                    Text { id: aiT; x: 22; width: parent.width - 22; wrapMode: Text.Wrap
                           text: shell.text("Also in: ") + (parent.parent.a && parent.parent.a.inUse ? parent.parent.a.inUse : "")
                           color: T.text2; font.family: T.font; font.pixelSize: 13 }
                }
            }
            Acts { id: cmpActs; x: 0; y: 14; width: detailPanel.half - 50; a: de.compareActs; which: "compare"; visible: de.compareOpen && a.shown }
            DetailView {
                det: de.compare
                visible: de.compareOpen
                x: 0; y: cmpActs.visible ? cmpActs.y + cmpActs.height + 8 : 14
                width: detailPanel.half; height: detailPanel.height - y
            }
            Acts { id: detActs; x: de.compareOpen ? detailPanel.half + 14 : 0; y: 14; width: detailPanel.half - 50
                   a: de.detailActs; which: "detail" }
            DetailView {
                det: de.detail
                x: detActs.x; y: detActs.visible ? detActs.y + detActs.height + 8 : 14
                width: detailPanel.half; height: detailPanel.height - y
            }
        }

        // ================= Deck list / deck info =================
        Item {
            id: listPanel
            x: area.xOf("list"); width: area.wList; height: area.height
            // „Lists“ on: the lists slide in from the top (the button sits at the top), deck list/info slide down –
            // grip in between (share is saved)
            readonly property real full: height - 14
            readonly property real hGap: 22
            property real dragFrac: -1
            readonly property real frac: dragFrac >= 0 ? dragFrac : de.listsSplit
            readonly property real listsT: root.listsOpen && de.listsLib !== null
                                           ? Math.max(150, Math.min(full - hGap - 220, (full - hGap) * frac)) : 0
            property real listsH: listsT
            Behavior on listsH { enabled: shell.animate && listPanel.dragFrac < 0
                                 NumberAnimation { duration: 380 * shell.speed; easing.type: Easing.OutCubic } }
            readonly property real y0: tabs.y + tabs.height + 8
            Row {
                id: tabs
                y: 14 + (listPanel.listsH > 0.5 ? listPanel.listsH + listPanel.hGap * Math.min(1, listPanel.listsH / 60) : 0)
                spacing: 8
                Btn { width: (listPanel.width - 8) / 2; height: 36; text: shell.text("Deck list"); checkable: true; checked: de.tab === 0; onClicked: de.setTab(0) }
                Btn { width: (listPanel.width - 8) / 2; height: 36; text: shell.text("Deck info"); checkable: true; checked: de.tab === 1; onClicked: de.setTab(1) }
            }
            // ---- Deck list ----
            Item {
                id: listTab
                y: listPanel.y0
                width: parent.width; height: listPanel.height - y
                visible: de.tab === 0
                Column {
                    id: lHead
                    width: parent.width; spacing: 8
                    Text { visible: de.commander !== ""; width: parent.width; wrapMode: Text.Wrap
                           text: de.commander; textFormat: Text.StyledText; color: T.text; font.family: T.font; font.pixelSize: 13 }
                    Btn { visible: de.swapText !== ""; width: parent.width; height: 34; text: de.swapText
                          tip: shell.text("Switch cards you own in another printing to your printing")
                          onClicked: de.useOwnedPrints() }
                    // filters (always there, even at 0; both at once = show both) – then „→ list ▾“ for everything shown
                    Flow {
                        width: parent.width; spacing: 6
                        Btn { height: 32; compact: true; width: implicitWidth + 16
                              checkable: true; checked: listTab.fMiss
                              navIcon: "missing"; text: listTab.nMissing + " " + shell.text("missing")
                              tip: shell.text("Show only the cards you're missing for this deck – the search then shows all cards")
                              onClicked: de.toggleListFilter("missing") }
                        Btn { height: 32; compact: true; width: implicitWidth + 16
                              checkable: true; checked: listTab.fUse
                              navIcon: "flag"; text: de.inUseCount + " " + shell.text("in other decks")
                              tip: shell.text("Only show the cards that are also in built decks – each row says which one")
                              onClicked: de.toggleListFilter("inuse") }
                        Btn { id: toListBtn; height: 32; compact: true; width: implicitWidth + 16; visible: listTab.filt !== ""
                              text: "→ " + shell.text("List") + "  ▾"
                              tip: shell.text("Put all shown cards on a wish or own list")
                              onClicked: { missMenu.items = de.missingTargets(); missMenu.openAt(toListBtn) } }
                    }
                }
                // filters live in the backend (visible at the top as „Deck list“ chips and deselectable there)
                readonly property bool fMiss: de.listFilter.indexOf("missing") >= 0
                readonly property bool fUse: de.listFilter.indexOf("inuse") >= 0
                readonly property string filt: fMiss && fUse ? "both" : (fMiss ? "missing" : (fUse ? "inuse" : ""))
                readonly property int nMissing: {
                    var n = 0, all = de.deckList
                    for (var i = 0; i < all.length; i++) if (!all[i].head && all[i].own === "✗") n += (all[i].n || 1)
                    return n
                }
                readonly property var shown: {
                    var all = de.deckList
                    if (filt === "") return all
                    var out = [], head = null
                    for (var i = 0; i < all.length; i++) {
                        var r = all[i]
                        if (r.head) { head = r; continue }
                        var hit = (fMiss && r.own === "✗") || (fUse && r.inUse && r.inUse.length > 0)
                        if (hit) { if (head) { out.push(head); head = null } out.push(r) }
                    }
                    return out
                }
                function shownKeys() {
                    var ks = []
                    for (var i = 0; i < shown.length; i++) if (!shown[i].head) ks.push(shown[i].k)
                    return ks
                }
                Rectangle {
                    id: listBox
                    y: lHead.height + (lHead.height > 0 ? 8 : 0)
                    width: parent.width; height: parent.height - y - listBtns.height - 8
                    // no frame (like the Sessions list): header line with a divider; the outline only shows while a card
                    // is dragged in
                    readonly property bool dropHere: ghost.visible && ghost.kind === "result" && ghost.over(listBox)
                    radius: 12
                    color: dropHere ? Qt.darker(T.surface, 1.1) : "transparent"
                    border.width: dropHere ? 2 : 0; border.color: T.text2
                    readonly property real wCount: 34
                    readonly property real wCost: de.listColumns[2] === "" ? 0 : Math.max(56, Math.min(96, width * 0.18))
                    readonly property real wPrice: 70
                    readonly property real wOwn: 40
                    readonly property real wName: width - 16 - wCount - wCost - wPrice - wOwn
                    function colX(c) { return 8 + [0, wCount, wCount + wName, wCount + wName + wCost, wCount + wName + wCost + wPrice][c] }
                    function colW(c) { return [wCount, wName, wCost, wPrice, wOwn][c] }
                    Repeater {   // column headers: click sorts (again = reversed)
                        model: de.listColumns
                        delegate: Item {
                            required property var modelData
                            required property int index
                            x: listBox.colX(index); y: 4; width: listBox.colW(index); height: 28
                            Text { anchors.fill: parent; leftPadding: 4; rightPadding: 4
                                   horizontalAlignment: index === 3 ? Text.AlignRight : (index === 4 || index === 0 ? Text.AlignHCenter : Text.AlignLeft)
                                   verticalAlignment: Text.AlignVCenter
                                   text: modelData + (de.listSort[0] === index ? (de.listSort[1] ? " ▾" : " ▴") : "")
                                   color: chh2.hovered ? T.text : T.muted; font.family: T.font; font.pixelSize: 12; font.bold: true }
                            HoverHandler { id: chh2; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: de.sortBy(index) }
                        }
                    }
                    Rectangle { y: 33; width: listBox.width; height: 1; color: T.line }
                    ListView {
                        ScrollHint {}
                        id: rows
                        x: 0; y: 36; width: listBox.width; height: listBox.height - y - 4
                        clip: true; boundsBehavior: Flickable.StopAtBounds
                        model: listTab.shown
                        delegate: Rectangle {
                            id: lr
                            required property var modelData
                            readonly property bool picking: !modelData.head && modelData.pick === true
                            width: rows.width; height: modelData.head ? 34 : 30 + pinBox.height
                            radius: picking ? 10 : 0
                            color: modelData.head ? "transparent" : (picking ? Qt.lighter(T.surface, 1.25) : (modelData.sel ? T.surface2 : (lrh.hovered ? Qt.lighter(T.surface, 1.12) : "transparent")))
                            border.width: picking ? 1 : 0; border.color: T.line2
                            Text {
                                visible: lr.modelData.head
                                x: 12; anchors.verticalCenter: parent.verticalCenter
                                text: lr.modelData.head ? lr.modelData.text : ""
                                color: T.text; font.family: T.font; font.pixelSize: 14; font.bold: true
                            }
                            HoverHandler { id: lrh; enabled: !lr.modelData.head; cursorShape: Qt.PointingHandCursor }
                            TapHandler {
                                enabled: !lr.modelData.head
                                onTapped: function (ev, b) { if (ev.position.y <= 30 && tapCount === 1) de.selectRow(lr.modelData.k) }
                                onDoubleTapped: de.changeRow(lr.modelData.k, 1)
                            }
                            DragHandler {
                                enabled: !lr.modelData.head && !lr.picking
                                target: null; dragThreshold: 10
                                property point last
                                onCentroidChanged: if (active) { last = centroid.scenePosition; ghost.move("row", lr.modelData.k, "− " + lr.modelData.name, last.x, last.y) }
                                onActiveChanged: if (!active) ghost.drop(last.x, last.y)
                            }
                            Item {   // pin open: all prints – click = take exactly this one
                                id: pinBox
                                visible: !lr.modelData.head
                                y: 30; x: 8; width: parent.width - 16
                                height: lr.picking ? pinCol.implicitHeight + 8 : 0
                                Behavior on height { enabled: shell.animate; NumberAnimation { duration: 240 * shell.speed; easing.type: Easing.OutCubic } }
                                clip: true
                                Column {
                                    id: pinCol
                                    width: parent.width; spacing: 6
                                    opacity: lr.picking ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: 200 } }
                                    Btn { visible: lr.modelData.pinned === true; height: 24; compact: true; width: implicitWidth + 20
                                          text: shell.text("any version"); onClicked: de.pinPrint(lr.modelData.k, "") }
                                    PrintPicker {
                                        width: parent.width
                                        fadeColor: Qt.lighter(T.surface, 1.25)
                                        prints: lr.picking ? de.pinRows : []
                                        onPicked: function (id) { de.pinPrint(lr.modelData.k, id) }
                                    }
                                }
                            }
                            Item {
                                visible: !lr.modelData.head
                                width: parent.width; height: 30
                                Text { x: listBox.colX(0); width: listBox.colW(0) - 6; height: parent.height; verticalAlignment: Text.AlignVCenter
                                       horizontalAlignment: Text.AlignRight; text: lr.modelData.count || ""
                                       color: T.text2; font.family: T.font; font.pixelSize: 13 }
                                // name (truncates first), followed in light grey by „(any)“ / „(SET #nr)“ and the pin
                                readonly property real nameRoom: listBox.colW(1) - 8 - (useRow.width > 0 ? useRow.width + 6 : 0) - 26
                                Text { id: nameT; x: listBox.colX(1) + 4; height: parent.height
                                       width: Math.min(implicitWidth, parent.nameRoom)   // the name has priority
                                       verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight; text: lr.modelData.name || ""
                                       color: lr.modelData.sel ? T.top : T.text; font.family: T.font; font.pixelSize: 14; font.bold: !!lr.modelData.alt }
                                Text { id: whereT; x: nameT.x + nameT.width + 6; height: parent.height
                                       width: Math.min(implicitWidth, Math.max(0, parent.nameRoom - nameT.width - 6)); elide: Text.ElideRight
                                       visible: width >= 34   // only if there is still room
                                       verticalAlignment: Text.AlignVCenter; text: lr.modelData.where || ""
                                       color: T.dim; font.family: T.font; font.pixelSize: 12 }
                                Item {   // pin as in the list editor: choose print / pin it
                                    x: whereT.x + whereT.width + 2; width: 24; height: parent.height
                                    NavIcon { anchors.centerIn: parent; width: 14; height: 14; key: lr.modelData.pinned ? "pinOn" : "pin"
                                              color: lr.modelData.pinned ? T.hi : (pnh.hovered ? "#9a9a9a" : "#5e5e5e"); play: pnh.hovered }
                                    HoverHandler { id: pnh; cursorShape: Qt.PointingHandCursor
                                        onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(lr.modelData.pinned ? shell.text("Exactly this print – click: choose another or back to any") : shell.text("Any print – click: choose one exact print"), p.x, p.y) } else shell.tip("", 0, 0) }
                                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; onTapped: de.openPinPick(lr.modelData.k) }
                                }
                                Row {   // which built deck the card is in – visible without hover
                                    id: useRow
                                    x: listBox.colX(2) - width - 4; anchors.verticalCenter: parent.verticalCenter
                                    spacing: 3
                                    readonly property var uses: lr.modelData.inUse || []
                                    Rectangle {
                                        visible: useRow.uses.length > 0
                                        height: 20; radius: 6; width: Math.min(110, ut.implicitWidth + 12)
                                        color: Qt.rgba(1, 1, 1, 0.06); border.width: 1; border.color: T.line2
                                        Text { id: ut; anchors.centerIn: parent; width: Math.min(98, implicitWidth); elide: Text.ElideRight
                                               text: useRow.uses.length ? "⚑ " + useRow.uses[0].deck : ""
                                               color: T.text2; font.family: T.font; font.pixelSize: 11 }
                                    }
                                    Text { visible: useRow.uses.length > 1; anchors.verticalCenter: parent.verticalCenter
                                           text: "+" + (useRow.uses.length - 1); color: T.muted; font.family: T.font; font.pixelSize: 11; font.bold: true }
                                }
                                Row {   // mana cost (hidden in games without it)
                                    visible: listBox.wCost > 0
                                    x: listBox.colX(2) + listBox.colW(2) - width - 6; anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Repeater { model: lr.modelData.mana || []
                                        Rectangle { required property var modelData; width: 16; height: 16; radius: 8; color: modelData.c
                                                    Text { anchors.centerIn: parent; text: modelData.s; color: T.onHi; font.pixelSize: 10; font.bold: true } } }
                                }
                                Text { x: listBox.colX(3); width: listBox.colW(3) - 4; height: parent.height; verticalAlignment: Text.AlignVCenter
                                       horizontalAlignment: Text.AlignRight; text: lr.modelData.price || ""
                                       color: T.text2; font.family: T.font; font.pixelSize: 13 }
                                Item {
                                    x: listBox.colX(4); width: listBox.colW(4); height: parent.height
                                    Text { anchors.centerIn: parent; text: lr.modelData.own || ""; color: lr.modelData.ownColor || T.text
                                           font.family: T.font; font.pixelSize: 13; font.bold: true
                                           visible: !(lr.modelData.holders && lr.modelData.holders.length) }
                                    Row {
                                        anchors.centerIn: parent; spacing: -5
                                        Repeater { model: lr.modelData.holders || []
                                            Image { required property var modelData; height: 22; width: 22 * 63 / 88; source: modelData.img; sourceSize.height: 88 } }
                                    }
                                    HoverHandler { onHoveredChanged: if (hovered && lr.modelData.ownTip) { var p = parent.mapToItem(null, parent.width / 2, parent.height); shell.tip(lr.modelData.ownTip, p.x, p.y) } else shell.tip("", 0, 0) }
                                }
                            }
                        }
                    }
                }
                Row {
                    id: listBtns
                    y: parent.height - height
                    spacing: 6
                    readonly property real bw: (listTab.width - 3 * 6) / 4
                    Btn { width: parent.bw; height: 36; text: "+1"; onClicked: de.changeCurrent(1) }
                    Btn { width: parent.bw; height: 36; text: "−1"; onClicked: de.changeCurrent(-1) }
                    Btn { width: parent.bw; height: 36; text: shell.text("Remove"); onClicked: de.changeCurrent(-999) }
                    Btn { width: parent.bw; height: 36; navIcon: "upgrade"; text: shell.text("Upgrades"); checkable: true; checked: de.upgradeMode
                          tip: shell.text("Cards from your collection that would improve this deck – click again = back to search")
                          onClicked: de.toggleUpgrades() }
                }
            }
            // ---- Deck info ----
            Flickable {
                ScrollHint {}
                id: infoTab
                y: listPanel.y0
                width: parent.width; height: listPanel.height - y
                visible: de.tab === 1
                contentHeight: info.height + 20
                clip: true; boundsBehavior: Flickable.StopAtBounds
                Mirror { id: info; width: infoTab.width - 10; mirror: de.stats }
            }
            // ---- Grip between deck list and lists ----
            Item {
                id: lSplit
                visible: listsBox.visible
                y: 14 + listPanel.listsH; width: parent.width; height: listPanel.hGap
                z: 5
                Rectangle { anchors.centerIn: parent; width: 46; height: 3; radius: 1.5
                            color: lsh.hovered || lsd.active ? T.text2 : T.line2 }
                HoverHandler { id: lsh; cursorShape: Qt.SplitVCursor }
                DragHandler {
                    id: lsd
                    target: null; xAxis.enabled: false
                    property real startH: 0
                    onActiveChanged: {
                        if (active) { startH = listPanel.listsT; listPanel.dragFrac = listPanel.frac }
                        else { de.setListsSplit(listPanel.listsT / (listPanel.full - listPanel.hGap)); listPanel.dragFrac = -1 }
                    }
                    onTranslationChanged: if (active) listPanel.dragFrac = Math.max(0.1, Math.min(0.9, (startH + translation.y) / (listPanel.full - listPanel.hGap)))
                }
            }
            // ---- Lists (as in the Library) ----
            Item {
                id: listsBox
                y: 14
                width: parent.width; height: listPanel.listsH
                visible: height > 2 && de.listsLib !== null
                clip: true
                ListsPanel {
                    id: listsInner
                    // hangs at the bottom of the window: slides in from the top when opened
                    width: parent.width; height: Math.max(parent.height, listPanel.listsT > 1 ? listPanel.listsT : 300)
                    y: parent.height - height
                    lib: de.listsLib
                    pickable: false
                    hintText: ""
                    onCloseRequested: root.listsOpen = false
                    onMenuRequested: function (kind, lid, sx, sy) {
                        listMenu.kind = kind; listMenu.lid = lid
                        listMenu.items = de.listsLib.listMenu(kind, lid)
                        var q = root.mapFromItem(null, sx, sy)
                        listMenu.open(q.x, q.y)
                    }
                }
            }
        }
    }

    // ================= Drag: result -> deck list, row -> results =================
    Item {
        id: ghost
        z: 90
        visible: false
        property string kind: ""
        property int what: -1
        property real sx: 0
        property real sy: 0
        x: sx - width / 2; y: sy - height / 2
        width: Math.min(280, gt.implicitWidth + 24); height: 32
        function move(k, w, text, px, py) {
            var p = root.mapFromItem(null, px, py)
            kind = k; what = w; sx = p.x; sy = p.y; gt.text = text; visible = true
            if (k === "row" && de.upgradeView && upView.item && upView.item.rowAt(px, py) >= 0)
                gt.text = "⇄ " + text.replace(/^− /, "")   // onto an upgrade pair: out instead of this one
            if (k === "row" && root.listsOpen) {
                var hit = listsInner.listAt(px, py)
                listsInner.dropKey = hit ? hit.kind + "|" + hit.id : ""
                if (hit) gt.text = "→ " + text.replace(/^− /, "")
            }
        }
        function over(item) {
            var p = item.mapFromItem(root, sx, sy)
            return item.visible && p.x >= 0 && p.y >= 0 && p.x <= item.width && p.y <= item.height
        }
        function drop(px, py) {
            if (!visible) return
            var p = root.mapFromItem(null, px, py)
            sx = p.x; sy = p.y
            visible = false
            if (kind === "result" && over(listBox)) {
                var lp = rows.mapFromItem(root, sx, sy)
                var idx = rows.indexAt(lp.x + rows.contentX, lp.y + rows.contentY)
                var row = idx >= 0 ? listTab.shown[idx] : null
                de.dropResult(what, row && !row.head ? row.board : "main")
            } else if (kind === "row" && root.listsOpen && listsInner.listAt(px, py)) {
                var hit = listsInner.listAt(px, py)
                listsInner.dropKey = ""
                de.rowToList(what, hit.kind, hit.id)
            } else if (kind === "row" && de.upgradeView && upView.item && upView.item.rowAt(px, py) >= 0) {
                // upgrades: drag a row from the deck list onto a pair = this card goes out
                var ui = upView.item.rowAt(px, py), dr = de.deckList[what]
                if (dr && !dr.head) de.upBridge.chooseOutSid(ui, dr.sid)
            } else if (kind === "row" && over(cardsPanel)) {
                de.dropRowOut(what)
            }
        }
        Rectangle {
            anchors.fill: parent; radius: 10; color: T.surface2; border.width: 1; border.color: T.line2; opacity: 0.95
            Text { id: gt; anchors.centerIn: parent; width: Math.min(256, implicitWidth); elide: Text.ElideRight
                   color: T.text; font.family: T.font; font.pixelSize: 13; font.bold: true }
        }
    }

    Shortcut { sequence: "Ctrl+S"; enabled: root.visible; onActivated: de.save() }
    Shortcut { sequence: "Ctrl+F"; enabled: root.visible; onActivated: sfield.focusAll() }
    ContextMenu {   // shown cards → list (in the window, no pop-up)
        id: missMenu
        z: 900
        onPicked: function (k) { de.rowsTo(k, listTab.shownKeys(), listTab.filt) }
    }
    property bool listsOpen: false
    ContextMenu {
        id: listMenu
        z: 900
        property string kind: ""
        property string lid: ""
        onPicked: function (k) { de.listsLib.listAction(kind, lid, k) }
    }
}
