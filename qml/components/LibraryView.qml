// Library view: header row (set progress, My collection/All cards, search, advanced search, sorting,
// cards per row, display), chips of the active filters, card grid with comparison and detail.
// lib: a LibraryBackend (qlibrary.py) – the Library itself or a view in Trade.
import QtQuick
import QtQuick.Window

Item {
    id: page
    property var lib
    property real pad: 20
    property real gridMinimum: Math.max(560, width / 4)
    property bool draggable: false
    clip: true   // detail, comparison and set progress glide in over the edge
    signal tileDoubleClicked(int index)
    signal tileDragMoved(int index, url img, real sx, real sy)
    signal tileDropped(int index, real sx, real sy)

    // ---------- Header row ----------
    Item {
        id: head
        z: 20
        x: page.pad; y: 14
        width: page.width - 2 * page.pad
        // two rows as soon as the search between the buttons left and right would no longer get at least 320 px
        // (previously fixed below 1280 px – at a 1366 px window nothing was left for the search, „Lists“ below „?“)
        readonly property bool narrow: width < left.width + rightRow.width + 20 + 320
        height: narrow ? 36 * 2 + 10 : 36

        Row {
            id: left
            spacing: 10
            Btn { glyph: "bars"; compact: true; height: 36; width: 44; active: lib.completionOpen; visible: lib.isMain
                  tip: shell.text("Set progress: how much of each set you own – slides in from the left (on/off)")
                  onClicked: lib.toggleCompletion() }
            Btn { text: shell.text("My collection"); width: Math.max(150, implicitWidth); checkable: true; checked: lib.mode === "mine"; visible: lib.showMine
                  onClicked: lib.setMode("mine") }
            Btn { text: shell.text("All cards"); width: Math.max(120, implicitWidth); checkable: true; checked: lib.mode === "all"; visible: lib.showAll
                  tip: shell.text("All cards from the card database (offline) – owned ones are marked")
                  onClicked: lib.setMode("all") }
            Btn { navIcon: "lists"; text: shell.text("Lists"); height: 36; width: implicitWidth   // as in deck building
                  checkable: true; checked: lib.listsOpen; visible: lib.isMain
                  tip: shell.text("Lists: wish and trade lists – slides in on the left (on/off)")
                  onClicked: lib.toggleLists() }
        }
        SearchField {
            id: search
            anchors.left: left.right; anchors.leftMargin: left.width > 0 ? 10 : 0
            anchors.right: head.narrow ? parent.right : rightRow.left; anchors.rightMargin: head.narrow ? 0 : 10
            placeholder: lib.searchHint || shell.text("Search: name, rules text, type, artist … or syntax like k:flying o:\"draw a card\"")
            text: lib.searchText
            onEdited: function (t) { lib.setSearch(t) }
            onAccepted: lib.commitSearch()
        }
        Row {
            id: rightRow
            spacing: 10
            anchors.right: parent.right
            y: head.narrow ? 46 : 0
            Btn { text: "?"; width: 36; compact: true; height: 36; tip: lib.syntaxHelp }
            Btn { text: lib.adv.buttonText + (lib.adv.open ? "  ▴" : "  ▾"); height: 36; active: lib.adv.open
                  enabled: lib.hasDb
                  tip: lib.hasDb ? "" : shell.text("Advanced search needs the card database (Settings).")
                  onClicked: lib.adv.setOpen(!lib.adv.open) }
            Btn {   // Group by: the tree opens in place below the head (Oliver, 29.10.)
                visible: lib.isMain
                navIcon: "group"; height: 36; width: Math.min(implicitWidth, 300)
                text: lib.group.buttonText + (lib.group.open ? "  ▴" : "  ▾")
                active: lib.group.open || lib.group.active
                tip: lib.group.enabled ? shell.text("Group your collection by set, rarity, type … – as a tree")
                                       : shell.text("Group by works in “My Collection”.")
                onClicked: lib.group.setOpen(!lib.group.open) }
            DropList {
                items: lib.sorts; current: lib.sort; width: 240; height: 36; listWidth: 400
                directional: true; dir: lib.sortDir; reversed: lib.sortReversed
                onPicked: function (k) { lib.setSort(k) }
                onPickedDir: function (k, d) { lib.setSortDir(k, d) }
                onReverse: lib.toggleSortDir()
            }
            Btn {   // several cards at once (Oliver, after 0.9.2) – like "Select" in the deck builder
                visible: lib.isMain
                height: 36; width: implicitWidth
                text: lib.sel.choosing ? shell.text("Done") : shell.text("Select")
                active: lib.sel.choosing
                tip: lib.sel.choosing ? shell.text("End the choice (Esc)")
                                      : shell.text("Choose several cards – then put them on a list, into a deck or in the trash (also Ctrl/Shift+click)")
                onClicked: lib.sel.toggleChoosing() }
            Rectangle {   // cards per row: in the box with the grid icon
                height: 36; width: slider.width + 46
                radius: 10; color: "transparent"; border.width: 1; border.color: T.line2
                Canvas {
                    onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up first paint
                    x: 12; anchors.verticalCenter: parent.verticalCenter
                    width: 16; height: 16
                    onPaint: { var g = getContext("2d"); g.reset(); g.strokeStyle = T.text2; g.lineWidth = 1.6
                        g.beginPath(); g.moveTo(5.5, 1); g.lineTo(5.5, 15); g.moveTo(10.5, 1); g.lineTo(10.5, 15)
                        g.moveTo(1, 5.5); g.lineTo(15, 5.5); g.moveTo(1, 10.5); g.lineTo(15, 10.5); g.stroke() }
                }
                StepSlider {
                    id: slider
                    x: 34; anchors.verticalCenter: parent.verticalCenter
                    width: 170
                    from: lib.colMin; to: lib.colMax; value: lib.columns
                    onMoved: function (v) { lib.setColumns(v) }
                }
            }
            Btn { glyph: "sliders"; compact: true; height: 36; width: 44
                  tip: shell.text("Display: how cards and lists look (settings)")
                  onClicked: lib.openDisplay() }
        }
    }

    AdvSearch {
        id: advPanel
        z: 15
        onAnimatingChanged: if (animating) area.topHold = area.y
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: head.bottom; anchors.topMargin: 10
        adv: lib.adv
    }
    GroupPanel {
        id: groupPanel
        z: 14
        g: lib.group
        onAnimatingChanged: if (animating) area.topHold = area.y
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: advPanel.bottom; anchors.topMargin: lib.group.open ? 10 : 0
    }
    // the chip row: the active filters – and "Group by" always at its right end (Oliver, 30.10.)
    Item {
        id: chipRow
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: groupPanel.bottom
        anchors.topMargin: lib.chips.length || lib.listChip || groupChips.shown ? 8 : 0
        height: Math.max(chips0.height, groupChips.height)
        ChipBar {
            id: chips0
            // a picked list: the chips move a little to the right while its rows slide in (review .101)
            property real shift: lib.isMain && lib.listBar ? 16 : 0
            Behavior on shift { enabled: shell.animate; NumberAnimation { duration: 220 * shell.speed; easing.type: Easing.OutCubic } }
            x: shift; width: chipRow.width - shift - (groupChips.shown ? groupChips.width + 10 : 0)
            groups: lib.chips
            lead: lib.listBar ? null : lib.listChip   // a picked list has its own tool row below
            onChipClicked: function (id) { lib.chip(id) }
            onLeadClicked: lib.clearList()
        }
        GroupChips {
            id: groupChips
            objectName: "groupChips"
            g: lib.group
            anchors.right: parent.right
        }
    }
    // extra chips (Trade: „have“, „missing“ …)
    Flow {
        id: chips
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: chipRow.bottom; anchors.topMargin: lib.extraChips.length ? 8 : 0
        height: lib.extraChips.length ? implicitHeight : 0
        spacing: 6
        Repeater {
            model: lib.extraChips
            delegate: Rectangle {
                required property var modelData
                height: 30; radius: 15
                width: xt.implicitWidth + 28
                color: modelData.on ? "#d9d9d9" : (xh.hovered ? T.surface2 : T.surface)
                border.width: 1; border.color: modelData.on ? "#d9d9d9" : (xh.hovered ? T.text2 : T.line2)
                Text { id: xt; anchors.centerIn: parent; text: modelData.text
                       color: modelData.on ? T.onHi : T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
                HoverHandler { id: xh; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: lib.toggleExtra(modelData.key) }
            }
        }
    }

    // ---------- picked list: edit it right here (Oliver, review .62, new in .101) ----------
    // Row 1: name (click = rename) · cards on the list · hidden by filters | right: Clear filters · ✕
    // Row 2: private · shared · price alert | right: the selected card −/n/+ and off the list
    // A click on a list: the rows slide in (the chips move a little to the right meanwhile), then the content fades in.
    // No "Search cards": you search as usual and drag cards onto the list.
    Item {
        id: listTools
        readonly property var bar: lib.isMain && lib.listBar ? lib.listBar : null   // undefined at start -> null
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: chips.bottom; anchors.topMargin: bar ? 10 : 0
        height: bar ? 80 : 0   // (no height animation: the grid below would be re-laid out every frame)
        visible: height > 0.5
        clip: !ltBody.renaming   // (the rename strip may hang out below)
        function rename() { if (ltLd.item) ltLd.item.rename() }
        Connections {
            target: lib
            function onRenameAsked(kind, lid) {
                if (listTools.bar && listTools.bar.kind === kind && listTools.bar.lid === lid) listTools.rename()
            }
        }
        QtObject { id: ltBody; property bool renaming: false }
        Loader {   // (built only while a list is open)
        id: ltLd
        width: parent.width; height: 80
        active: listTools.bar !== null
        sourceComponent: Item {
        id: ltIn
        function rename() { lname.start() }
        opacity: 0
        transform: Translate { id: ltSlide; y: shell.animate ? -14 : 0 }
        Component.onCompleted: fadeIn.start()
        ParallelAnimation {   // the rows slide in (chips move right meanwhile), the content fades in a moment later
            id: fadeIn
            NumberAnimation { target: ltSlide; property: "y"; to: 0; duration: shell.animate ? 220 * shell.speed : 0
                              easing.type: Easing.OutCubic }
            SequentialAnimation {
                PauseAnimation { duration: shell.animate ? 120 * shell.speed : 0 }
                NumberAnimation { target: ltIn; property: "opacity"; to: 1; duration: shell.animate ? 200 * shell.speed : 0 }
            }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line }
        Row {
            id: ltLeft
            y: 4; height: 32
            z: 5   // (the rename strip hangs over row 2)
            spacing: 10
            Btn { height: 32; compact: true; visible: shell.backKey !== "" && shell.backKey !== "library"
                  text: "← " + (shell.navItems.find(function (n) { return n.key === shell.backKey }) || {text: ""}).text
                  onClicked: shell.goBack() }
            RenameField {
                id: lname
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, 320); height: 28
                text: listTools.bar ? listTools.bar.name : ""
                color: T.hi; pixelSize: 17; bold: true
                onEditingChanged: ltBody.renaming = editing
                commit: function (v) { return lib.renameListTo(listTools.bar.kind, listTools.bar.lid, v) }
            }
            Text { anchors.verticalCenter: parent.verticalCenter
                   text: listTools.bar ? shell.text("%1 cards on the list").arg(listTools.bar.total) : ""
                   color: T.dim; font.family: T.font; font.pixelSize: 13 }
            Text { anchors.verticalCenter: parent.verticalCenter; visible: listTools.bar !== null && listTools.bar.hidden > 0
                   text: listTools.bar ? "· " + shell.text("%1 hidden by search or filters").arg(listTools.bar.hidden) : ""
                   color: T.text2; font.family: T.font; font.pixelSize: 13 }
        }
        Row {
            anchors.right: parent.right; y: 4; height: 32
            spacing: 6
            Btn { height: 30; compact: true; anchors.verticalCenter: parent.verticalCenter
                  visible: listTools.bar !== null && listTools.bar.hidden > 0
                  text: shell.text("Clear all filters"); onClicked: lib.clearFilters() }
            Btn { height: 32; width: 32; compact: true; glyph: "close"; tip: shell.text("Show all cards again")
                  onClicked: lib.clearList() }
        }
        Row {   // row 2: who sees the list, price alert
            y: 42; height: 30
            spacing: 6
            Btn { height: 30; compact: true; checkable: true; visible: !!listTools.bar && listTools.bar.shareable
                  text: shell.text("private"); checked: !!listTools.bar && !listTools.bar.shared
                  onClicked: lib.setShared(listTools.bar.kind, listTools.bar.lid, false) }
            Btn { height: 30; compact: true; checkable: true; visible: !!listTools.bar && listTools.bar.shareable
                  text: shell.text("shared"); checked: !!listTools.bar && listTools.bar.shared
                  onClicked: lib.setShared(listTools.bar.kind, listTools.bar.lid, true) }
            Btn { height: 30; compact: true; navIcon: "bell"; text: shell.text("Price alert")
                  active: !!listTools.bar && listTools.bar.alarm
                  tip: shell.text("Opens the list's price alert under Orbit → Price alerts"); onClicked: lib.listAlarm() }
        }
        Row {   // row 2, right: the selected card on this list (the pin sits in the lists column – review .101)
            anchors.right: parent.right; y: 42; height: 30
            spacing: 6
            visible: listTools.bar !== null && listTools.bar.card !== ""
            Text { anchors.verticalCenter: parent.verticalCenter; text: listTools.bar ? listTools.bar.card : ""
                   width: Math.min(implicitWidth, 200); elide: Text.ElideRight
                   color: T.text2; font.family: T.font; font.pixelSize: 13 }
            Btn { height: 30; width: 30; compact: true; text: "−"; visible: !!listTools.bar && listTools.bar.inList
                  onClicked: lib.listStep(-1) }
            Text { anchors.verticalCenter: parent.verticalCenter; visible: !!listTools.bar && listTools.bar.inList
                   text: listTools.bar ? listTools.bar.n + "×" : ""; color: T.text; font.family: T.font
                   font.pixelSize: 14; font.bold: true }
            Btn { height: 30; width: listTools.bar && listTools.bar.inList ? 30 : implicitWidth; compact: true
                  text: listTools.bar && listTools.bar.inList ? "+" : shell.text("+ Put on the list")
                  enabled: !(listTools.bar && (listTools.bar.auto || !listTools.bar.more))
                  tip: listTools.bar && !listTools.bar.more ? shell.text("All your copies are already on the list") : ""
                  onClicked: lib.listStep(1) }
            Btn { height: 30; compact: true; visible: !!listTools.bar && listTools.bar.inList
                  text: shell.text("Remove from the list"); onClicked: lib.listStep(0) }
        }
        }
        }
    }

    // ---------- several cards chosen: the action row (content makes room – like the list's tool row) ----------
    // "n cards chosen · value" · To list ▾ · To deck ▾ · For trade · Change ▾ · To the trash | All · None · ✕
    Item {
        id: selTools
        readonly property bool on: lib.isMain && lib.sel.active
        x: page.pad; width: page.width - 2 * page.pad
        anchors.top: listTools.bottom; anchors.topMargin: on ? 10 : 0
        height: on ? 44 : 0   // (no height animation: the grid would be re-laid out every frame)
        visible: on
        Loader {
            anchors.fill: parent
            active: selTools.on
            sourceComponent: Item {
                id: stIn
                opacity: 0
                transform: Translate { id: stSlide; y: shell.animate ? -12 : 0 }
                Component.onCompleted: stAnim.start()
                ParallelAnimation {
                    id: stAnim
                    NumberAnimation { target: stSlide; property: "y"; to: 0; duration: shell.animate ? 200 * shell.speed : 0; easing.type: Easing.OutCubic }
                    NumberAnimation { target: stIn; property: "opacity"; to: 1; duration: shell.animate ? 200 * shell.speed : 0 }
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: T.line }
                Row {
                    anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -3
                    spacing: 8
                    Text { anchors.verticalCenter: parent.verticalCenter; text: lib.sel.info
                           color: T.hi; font.family: T.font; font.pixelSize: 15; font.bold: true }
                    Rectangle { width: 1; height: 22; color: T.line; anchors.verticalCenter: parent.verticalCenter }
                    Row { spacing: 8; enabled: lib.sel.count > 0; opacity: enabled ? 1 : 0.45   // nothing chosen yet: greyed
                    Btn { id: sbList; height: 32; compact: true; text: shell.text("To list") + "  ▾"
                          onClicked: { selMenu.what = "list"; selMenu.items = lib.sel.listTargets(); selMenu.openAt(sbList) } }
                    Btn { id: sbDeck; height: 32; compact: true; text: shell.text("To deck") + "  ▾"
                          onClicked: { selMenu.what = "deck"; selMenu.items = lib.sel.deckTargets(); selMenu.openAt(sbDeck) } }
                    Btn { height: 32; compact: true; visible: lib.sel.ownCopies; text: shell.text("For trade")
                          tip: shell.text("Mark the chosen copies for trade (trade list)"); onClicked: lib.sel.toTrade() }
                    Btn { id: sbChange; height: 32; compact: true; visible: lib.sel.ownCopies; text: shell.text("Change") + "  ▾"
                          tip: shell.text("Condition, language or finish – for all chosen copies")
                          onClicked: { selMenu.what = "change"; selMenu.items = lib.sel.changeTargets(); selMenu.openAt(sbChange) } }
                    Btn { height: 32; compact: true; visible: lib.sel.ownCopies; danger: true; text: shell.text("To the trash")
                          onClicked: lib.sel.trash() }
                    }
                }
                Row {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -3
                    spacing: 6
                    Btn { height: 32; compact: true; text: shell.text("All"); enabled: !lib.sel.allChosen
                          tip: shell.text("Everything shown (Ctrl+A)"); onClicked: lib.sel.all() }
                    Btn { height: 32; compact: true; text: shell.text("None"); onClicked: lib.sel.none() }
                    Btn { height: 32; width: 32; compact: true; glyph: "close"; tip: shell.text("End the choice (Esc)")
                          onClicked: lib.sel.end() }
                }
            }
        }
    }
    ContextMenu {
        id: selMenu
        z: 900
        property string what: ""
        onPicked: function (k) {
            if (what === "list") lib.sel.toList(k)
            else if (what === "deck") lib.sel.toDeck(k)
            else if (what === "change") lib.sel.change(k)
        }
    }

    // ---------- Grid | comparison | detail ----------
    Item {
        id: area
        x: page.pad
        width: page.width - 2 * page.pad
        // position: follows the advanced search (only shifted). Height: fixed while the search slides out/in (the
        // larger of before/after, the rest disappears below the status bar) – otherwise grid and views would be
        // re-laid out every frame (stutters); afterwards the correct height once
        y: selTools.y + selTools.height + 12
        readonly property real bottomY: status.y - 6
        readonly property real topFinal: y + advPanel.targetH - advPanel.height + groupPanel.targetH - groupPanel.height
        property real topHold: 0
        readonly property bool sliding: advPanel.animating || groupPanel.animating   // (the group strip slides the same way)
        height: sliding ? bottomY - Math.min(topFinal, topHold) : bottomY - y
        readonly property real gridMin: page.gridMinimum
        // state the grid is currently laid out for (set by syncLayout: first remember previous places, then re-lay)
        property bool layDet: false
        property bool morphing: false   // grid is re-laying out (the scrollbar may then follow softly)
        Timer { id: morphOff; interval: 700; onTriggered: area.morphing = false }
        property bool layCmp: false
        property bool layComp: false
        property real dragW: -1
        readonly property real wantW: dragW > 0 ? dragW : lib.detailWidth
        readonly property real panelW: Math.max(360, Math.min(wantW, (width - gridMin - (layCmp ? 14 : 0)) / (layCmp ? 2 : 1)))
        property real compDrag: -1
        readonly property real compWant: Math.max(300, Math.min(compDrag > 0 ? compDrag : lib.completionWidth, width * 0.4))
        // target (the grid follows it) and visible position of the views (glide after – when gliding
        // immediately, on focus only in their time window: pDelay/pDur)
        readonly property real detT: layDet ? panelW : 0
        readonly property real cmpT: layCmp ? panelW : 0
        readonly property real compT: layComp ? compWant : 0
        readonly property real compGap: 24   // set progress/lists ↔ grid
        property bool visDet: false
        property bool visCmp: false
        property bool visComp: false
        property real pDelay: 0
        property real pDur: 460 * shell.speed
        property real detW: visDet ? panelW : 0
        property real cmpW: visCmp ? panelW : 0
        property real compW: visComp ? compWant : 0
        Behavior on compW { enabled: shell.animate && area.compDrag < 0; SequentialAnimation {
            PauseAnimation { duration: area.pDelay }
            NumberAnimation { duration: area.pDur; easing.type: Easing.OutBack; easing.overshoot: 0.9 } } }
        Behavior on detW { enabled: shell.animate && area.dragW < 0; SequentialAnimation {
            PauseAnimation { duration: area.pDelay }
            NumberAnimation { duration: area.pDur; easing.type: Easing.OutBack; easing.overshoot: 0.9 } } }
        Behavior on cmpW { enabled: shell.animate && area.dragW < 0; SequentialAnimation {
            PauseAnimation { duration: area.pDelay }
            NumberAnimation { duration: area.pDur; easing.type: Easing.OutBack; easing.overshoot: 0.9 } } }
    }
    DetailView {   // glides in from the right (at full width right away: the content doesn't rewrap on the way)
        id: detailView
        z: 3
        det: lib.detail
        x: area.x + area.width - area.detW
        y: area.y; height: area.height
        width: area.panelW
        visible: area.detW > 1
        holdCard: area.detW < area.panelW - 1 || page.fPhase > 0   // still gliding in: card stands still with it
        opacity: page.snapShown ? 0 : 1   // side swap: meanwhile the snapshots glide
    }
    Rectangle {   // shadow on the left of the detail view while it glides (also on top during the swap)
        z: 3
        x: page.snapShown ? snapL.x - 18 : detailView.x - 18
        y: area.y; width: 18; height: area.height
        visible: opacity > 0.01 && area.detW > 1
        opacity: page.snapShown ? Math.sin(Math.PI * page.swapK) : (area.detW < area.panelW - 1 ? 1 : 0)
        gradient: Gradient { orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(0, 0, 0, 0) }
            GradientStop { position: 1; color: Qt.rgba(0, 0, 0, 0.35) } }
    }
    // the comparison: built only while it slides out or is open (null otherwise – the users check for that).
    // The Loader has no size and sits at 0,0: the view keeps its own coordinates in the page
    readonly property Item compareView: compareLd.item
    Loader {
        id: compareLd
        z: 2
        active: area.cmpW > 1
        sourceComponent: DetailView {   // slides out from under the detail view or back under it
            z: 2
            det: lib.compare
            x: detailView.x - area.cmpW - 14 * Math.min(1, Math.max(0, area.cmpW / area.panelW))
            y: area.y; height: area.height
            width: area.panelW
            holdCard: area.cmpW < area.panelW - 1 || page.fPhase > 0
            opacity: page.snapShown ? 0 : 1
            onSwapRequested: page.beginSwap()
        }
    }
    // ---------- ⇄ Side swap: as before, as a „film“ ----------
    // Both views are snapshotted, then Python swaps (reloading everything). The snapshots glide – the left
    // content on top to the right, the right one below to the left –, and only when the real views are ready
    // are they shown again (they look the same). Only Pin and ⇄ change: old out (until 20 %), new in (from 75 %).
    property bool swapping: false
    property bool snapShown: false
    property real swapK: 1
    property real swapLX: 0
    property real swapRX: 0
    property bool swapPinned: false
    property url shotL
    property url shotR
    Image {   // snapshot of the right view (detail) – slides below to the left
        id: snapR
        z: 3.4
        source: page.shotR; cache: false; smooth: true
        visible: page.snapShown
        width: detailView.width; height: detailView.height; y: detailView.y
        x: page.swapRX + (page.swapLX - page.swapRX) * page.swapK
        transform: Scale { origin.x: snapR.width / 2; origin.y: snapR.height / 2
                           xScale: 1 - 0.06 * Math.sin(Math.PI * page.swapK); yScale: xScale }
    }
    Image {   // snapshot of the left view (comparison) – glides on top to the right
        id: snapL
        z: 3.6
        source: page.shotL; cache: false; smooth: true
        visible: page.snapShown
        width: compareView ? compareView.width : 0; height: compareView ? compareView.height : 0
        y: compareView ? compareView.y : 0
        x: page.swapLX + (page.swapRX - page.swapLX) * page.swapK
    }
    // Pin/⇄ travel with their snapshot: old fades out (until 20 %), new in (from 75 %). Each button has its fixed
    // icon – switching the icon would make it visibly morph over from the state of the last animation
    readonly property real ghostOut: Math.max(0, 1 - swapK / 0.2)
    readonly property real ghostIn: Math.max(0, (swapK - 0.75) / 0.25)
    Btn { z: 3.5; visible: page.swapping && page.swapPinned; opacity: page.ghostOut; width: 36; height: 36; compact: true
          x: snapR.x + detailView.pinX; y: snapR.y + detailView.pinY; glyph: "pinOn"; inverted: true }
    Btn { z: 3.5; visible: page.swapping && !page.swapPinned; opacity: page.ghostOut; width: 36; height: 36; compact: true
          x: snapR.x + detailView.pinX; y: snapR.y + detailView.pinY; glyph: "pin" }
    Btn { z: 3.5; visible: page.swapping; opacity: page.ghostIn; width: 36; height: 36; compact: true
          x: snapR.x + detailView.pinX; y: snapR.y + detailView.pinY; glyph: "swap" }
    Btn { z: 3.7; visible: page.swapping; opacity: page.ghostOut; width: 36; height: 36; compact: true
          x: snapL.x + (compareView ? compareView.pinX : 0); y: snapL.y + (compareView ? compareView.pinY : 0); glyph: "swap" }
    Btn { z: 3.7; visible: page.swapping; opacity: page.ghostIn; width: 36; height: 36; compact: true
          x: snapL.x + (compareView ? compareView.pinX : 0); y: snapL.y + (compareView ? compareView.pinY : 0); glyph: "pinOn"; inverted: true }
    function beginSwap() {
        if (swapping) return
        if (!shell.animate || !lib.compareOpen || !compareView) { lib.compare.setPinned(true); return }
        // the travelling buttons now sit exactly over the real ones (else they'd be missing for a frame or two,
        // until the snapshots are ready)
        swapLX = compareView.x; swapRX = detailView.x; swapK = 0
        swapPinned = lib.detail.pinned
        swapping = true
        detailView.hidePin = true; compareView.hidePin = true   // snapshots without Pin/⇄ (we fade those ourselves)
        shotL = ""; shotR = ""
        var dpr = Screen.devicePixelRatio || 1
        compareView.grabToImage(function (r) { page.shotL = r.url; page.swapGo() },
                                Qt.size(compareView.width * dpr, compareView.height * dpr))
        detailView.grabToImage(function (r) { page.shotR = r.url; page.swapGo() },
                               Qt.size(detailView.width * dpr, detailView.height * dpr))
    }
    function swapGo() {   // both snapshots ready: show, let Python swap (underneath, invisible), start gliding
        if (shotL.toString() === "" || shotR.toString() === "" || snapShown) return
        if (!compareView) return
        swapLX = compareView.x; swapRX = detailView.x
        swapK = 0
        snapShown = true
        lib.compare.setPinned(true)
        swapAnim.restart()
    }
    NumberAnimation { id: swapAnim; target: page; property: "swapK"; from: 0; to: 1
                      duration: 500 * shell.speed; easing.type: Easing.InOutCubic
                      onFinished: { swapWait.n = 0; swapWait.restart() } }
    Timer {   // landed: wait until both real views are ready (at most 1.5 s), then back invisibly
        id: swapWait; interval: 30; repeat: true
        property int n: 0
        onTriggered: {
            n++
            if ((detailView.ready && (!compareView || compareView.ready)) || n > 50) {
                stop()
                detailView.hidePin = false; if (compareView) compareView.hidePin = false
                page.snapShown = false; page.swapping = false; page.swapK = 1
            }
        }
    }
    Item {   // grip: drag the detail view wider/narrower
        id: grip
        z: 3
        visible: area.detW > 1
        x: (area.cmpW > 1 && compareView ? compareView.x : detailView.x) - 12
        y: area.y; height: area.height; width: 10
        Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5
                    color: gh.hovered || gd.active ? T.text2 : T.line2 }
        HoverHandler { id: gh; cursorShape: Qt.SplitHCursor }
        DragHandler {
            id: gd
            target: null; yAxis.enabled: false
            property real startW: 0
            onActiveChanged: {
                if (active) startW = area.panelW
                else { lib.setDetailWidth(Math.round(area.panelW)); area.dragW = -1 }
            }
            onTranslationChanged: if (active) area.dragW = Math.max(360, startW - translation.x / (lib.compareOpen ? 2 : 1))
        }
    }
    // Left column: set progress and lists. One open = full height; both = half each, the last opened on top
    // (slides in from the top, the other becomes half as tall). If one closes, the other grows again.
    Item {
        id: side
        readonly property bool cO: lib.completionOpen
        readonly property bool lO: lib.listsOpen
        readonly property real gap: 20
        readonly property real half: (area.height - gap) / 2
        // both closed: the last open one stays at full height while the column glides out
        property bool compAlive: cO
        property bool listsAlive: lO
        function sync() {
            if (cO) compAlive = true; else if (lO) compAlive = false
            if (lO) listsAlive = true; else if (cO) listsAlive = false
        }
        onCOChanged: sync()
        onLOChanged: sync()
        // both open: share of the upper one via the grip in between (saved)
        property real dragFrac: -1
        readonly property real frac: dragFrac >= 0 ? dragFrac : lib.sideSplit
        readonly property real topT: Math.max(160, Math.min(area.height - gap - 160, (area.height - gap) * frac))
        readonly property real botT: area.height - gap - topT
        readonly property bool compTop: lib.sideTop !== "lists"
        // target heights (the content arranges itself at once) and visible heights (glide after)
        readonly property real compT: cO ? (lO ? (compTop ? topT : botT) : area.height) : (lO ? 0 : (compAlive ? area.height : 0))
        readonly property real listsT: lO ? (cO ? (compTop ? botT : topT) : area.height) : (cO ? 0 : (listsAlive ? area.height : 0))
        property real compH: compT
        property real listsH: listsT
        Behavior on compH { enabled: shell.animate && side.dragFrac < 0; NumberAnimation { duration: 440 * shell.speed; easing.type: Easing.OutCubic } }
        Behavior on listsH { enabled: shell.animate && side.dragFrac < 0; NumberAnimation { duration: 440 * shell.speed; easing.type: Easing.OutCubic } }
        readonly property real compY: lib.sideTop === "lists" && listsH > 0.5 ? listsH + gap * Math.min(1, listsH / half) : 0
        readonly property real listsY: lib.sideTop !== "lists" && compH > 0.5 ? compH + gap * Math.min(1, compH / half) : 0
    }
    // Each field has its target height right away; a travelling window reveals it. The upper one hangs at the bottom
    // of its window – so it slides in from the top –, the lower one at the top.
    Item {
        id: compPanel
        z: 2
        x: area.x + area.compW - area.compWant
        y: area.y + side.compY; height: side.compH
        width: area.compWant
        visible: area.compW > 1 && side.compH > 1
        clip: true
        // (like the lists: only exists while shown – then kept 60 s)
        property bool warm: false
        onVisibleChanged: if (visible) { warm = true; compCool.stop() } else compCool.restart()
        Timer { id: compCool; interval: 60000; onTriggered: compPanel.warm = false }
        Loader {
            asynchronous: true   // built while the column slides in
            active: compPanel.visible || compPanel.warm
            width: parent.width; height: Math.max(parent.height, Math.min(380, side.compT > 1 ? side.compT : side.half))
            y: parent.height - height
            sourceComponent: CompletionPanel {
            // grows/shrinks with the window (bottom edge stays put); only below 380 px it is covered instead of
            // squeezed – so it slides in from the top when opening
            cp: lib.completion
            onCloseRequested: lib.toggleCompletion()
            onMenuRequested: function (sx, sy) {
                missMenu.items = lib.completion.missingTargets()
                var q = page.mapFromItem(null, sx, sy)
                missMenu.open(q.x, q.y)
            }
        }
        }
    }
    Item {
        id: listsPanel
        z: 2
        x: area.x + area.compW - area.compWant
        y: area.y + side.listsY; height: side.listsH
        width: area.compWant
        visible: area.compW > 1 && side.listsH > 1
        clip: true
        // the lists only exist while the column is shown – then kept 60 s (closing and re-opening stays instant)
        property bool warm: false
        onVisibleChanged: if (visible) { warm = true; listsCool.stop() } else listsCool.restart()
        Timer { id: listsCool; interval: 60000; onTriggered: listsPanel.warm = false }
        Loader {
            id: listsLoader
            asynchronous: true   // built while the column slides in
            active: listsPanel.visible || listsPanel.warm
            width: parent.width; height: Math.max(parent.height, Math.min(220, side.listsT > 1 ? side.listsT : side.half))
            y: parent.height - height
            sourceComponent: listsComp
        }
    }
    Component {
        id: listsComp
        ListsPanel {
            lib: page.lib
            onCloseRequested: lib.toggleLists()
            onMenuRequested: function (kind, lid, sx, sy) {
                listMenu.kind = kind; listMenu.lid = lid
                listMenu.items = lib.listMenu(kind, lid)
                var q = page.mapFromItem(null, sx, sy)
                listMenu.open(q.x, q.y)
            }
        }
    }
    ContextMenu {   // set progress: „Missing → list ▾“
        id: missMenu
        z: 900
        onPicked: function (k) { lib.completion.missingTo(k) }
    }
    // „⋯“ menu of a list (at page level, so it isn't clipped at the edge of the column)
    ContextMenu {
        id: listMenu
        z: 900
        property string kind: ""
        property string lid: ""
        onPicked: function (k) { lib.listAction(kind, lid, k) }
    }
    // drag a card from the grid onto a list (list column open): the card travels along, the list below glows
    property int dragMany: 0   // dragging one of several chosen cards: all of them go (the ghost is a stack)
    Image {
        id: listGhost
        z: 60
        visible: false
        Repeater {   // the stack behind it
            model: page.dragMany > 1 ? 2 : 0
            Rectangle { required property int index; z: -1; x: 5 * (index + 1); y: -5 * (index + 1)
                        width: listGhost.width; height: listGhost.height; radius: 7
                        color: T.surface2; border.width: 1; border.color: T.line2 }
        }
        Rectangle {   // how many
            visible: page.dragMany > 1
            anchors.right: parent.right; anchors.rightMargin: -8; y: -10
            width: Math.max(26, mc.implicitWidth + 14); height: 26; radius: 13
            color: T.text
            Text { id: mc; anchors.centerIn: parent; text: page.dragMany; color: T.surface
                   font.family: T.font; font.pixelSize: 13; font.bold: true }
        }
        width: 96; height: 134
        opacity: 0.88
        sourceSize.width: 200
        smooth: true
    }
    function ghostMove(img, sx, sy) {
        if (!(lib.isMain && lib.listsOpen)) return
        var q = page.mapFromItem(null, sx, sy)
        listGhost.source = img
        listGhost.x = q.x - listGhost.width / 2; listGhost.y = q.y - listGhost.height / 2
        listGhost.visible = true
        var li = listsLoader.item
        if (!li) return
        var hit = li.listAt(sx, sy)
        li.dropKey = hit ? hit.kind + "|" + hit.id : ""
    }
    function ghostDrop(sx, sy) {   // -> the list under the mouse ({kind, id}) or null
        if (!listGhost.visible) return null
        var li = listsLoader.item
        var hit = li ? li.listAt(sx, sy) : null
        listGhost.visible = false
        if (li) li.dropKey = ""
        return hit
    }
    Connections {
        target: page
        function onTileDragMoved(i, img, sx, sy) { page.ghostMove(img, sx, sy) }
        function onTileDropped(i, sx, sy) {
            var hit = page.ghostDrop(sx, sy), many = page.dragMany
            page.dragMany = 0
            if (!hit) return
            if (many > 1) lib.sel.toList(hit.kind + ":" + hit.id)   // a chosen card drags all chosen ones
            else lib.dropOnList(i, hit.kind, hit.id)
        }
    }
    Connections {   // the card of the detail view
        target: detailView
        function onCardDragMoved(sx, sy) { page.ghostMove(lib.detail.imageUrl, sx, sy) }
        function onCardDropped(sx, sy) { var hit = page.ghostDrop(sx, sy); if (hit) lib.dropShownOnList(false, hit.kind, hit.id) }
    }
    Connections {   // … and of the comparison (exists only while it is open)
        target: page.compareView
        ignoreUnknownSignals: true
        function onCardDragMoved(sx, sy) { page.ghostMove(lib.compare.imageUrl, sx, sy) }
        function onCardDropped(sx, sy) { var hit = page.ghostDrop(sx, sy); if (hit) lib.dropShownOnList(true, hit.kind, hit.id) }
    }
    Item {   // grip between set progress and lists (both open): split the height
        z: 3
        visible: area.compW > 1 && side.cO && side.lO && side.compH > 1 && side.listsH > 1
        x: compPanel.x; width: compPanel.width; height: side.gap + 8
        y: area.y + (side.compTop ? side.compH : side.listsH) + side.gap / 2 - height / 2
        Rectangle { anchors.centerIn: parent; width: 46; height: 3; radius: 1.5; color: sgh.hovered || sgd.active ? T.text2 : T.line2 }
        HoverHandler { id: sgh; cursorShape: Qt.SplitVCursor }
        DragHandler {
            id: sgd
            target: null; xAxis.enabled: false
            property real startH: 0
            onActiveChanged: {
                if (active) { startH = side.topT; side.dragFrac = side.frac }
                else { lib.setSideSplit(side.topT / (area.height - side.gap)); side.dragFrac = -1 }
            }
            onTranslationChanged: if (active) side.dragFrac = Math.max(0.1, Math.min(0.9, (startH + translation.y) / (area.height - side.gap)))
        }
    }
    Item {   // grip of the set progress
        z: 2
        visible: area.compW > 1
        x: compPanel.x + compPanel.width + (area.compGap + 8) / 2 - 5   // centred between window and card (8 px padding)
        y: area.y; height: area.height; width: 10
        Rectangle { anchors.centerIn: parent; width: 3; height: 46; radius: 1.5; color: cgh.hovered || cgd.active ? T.text2 : T.line2 }
        HoverHandler { id: cgh; cursorShape: Qt.SplitHCursor }
        DragHandler {
            id: cgd
            target: null; yAxis.enabled: false
            property real startW: 0
            onActiveChanged: {
                if (active) startW = area.compW
                else { lib.setCompletionWidth(Math.round(area.compW)); area.compDrag = -1 }
            }
            onTranslationChanged: if (active) area.compDrag = Math.max(300, startW + translation.x)
        }
    }
    GridView {
        EdgeFade {}
        // only the mouse wheel (the bar here is sbar – it travels along on focus); one notch ≈ one card row
        ScrollHint { visible: false; wheelStep: Math.max(150, grid.cellHeight * 0.9) }
        id: grid
        x: area.x + (area.compT > 1 ? area.compT + area.compGap : 0)
        clip: !page.fFlying   // during the focus flight the card may go over the edge of the grid
        width: Math.max(100, area.width - area.compT - (area.compT > 1 ? area.compGap : 0) - area.detT - area.cmpT - (area.detT > 1 ? 16 : 0) - (area.cmpT > 1 ? 14 : 0))
        y: area.y; height: area.height
        model: lib.model
        // tiles outside the view: about 60 cards in each direction (few rows with many columns, more with few),
        // 2–8 rows – keeps images for scrolling back without holding hundreds in memory with small tiles
        cacheBuffer: Math.round(Math.max(2, Math.min(8, 60 / Math.max(1, cols))) * cellHeight)
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3500
        maximumFlickVelocity: 6000
        property int cols: 1   // set by syncLayout
        cellWidth: Math.floor((width - 12) / cols)
        readonly property real cw: cellWidth - 16
        readonly property int npx: Math.max(10, Math.min(16, Math.round(cw / 13)))
        cellHeight: Math.round(cw * 88 / 63) + Math.round(npx * 2.8) + 14
        property int appearGen: 0
        property int appearFirst: 0
        onAtYEndChanged: if (atYEnd) lib.fetchMore()
        // "All cards" loads the visible rows and one more (Oliver, after 0.9.2): the library is told how many rows fit,
        // and the next page comes once the last loaded row is about to scroll in
        readonly property int viewRows: Math.max(1, Math.ceil(height / Math.max(1, cellHeight)))
        onViewRowsChanged: { if (lib.setViewRows) lib.setViewRows(viewRows); if (contentHeight < height + cellHeight) lib.fetchMore() }
        Component.onCompleted: if (lib.setViewRows) lib.setViewRows(viewRows)
        // load images from the first visible card first (qlibrary.viewTop -> quickimages.prioritize)
        onContentYChanged: { topTimer.restart(); if (contentY + height > contentHeight - cellHeight) lib.fetchMore() }
        Timer { id: topTimer; interval: 120; onTriggered: if (page.lib && page.lib.viewTop) page.lib.viewTop(grid.indexAt(10, grid.contentY + 10)) }


        delegate: CardTile {
            id: tile
            // all shown values in one call (qlibrary.CardGridModel.TILE) – each role is a call into Python
            readonly property var tv: model.tile || ({})
            name: tv.name || ""
            price: tv.price || ""
            setLine: tv.setLine || ""
            chips: tv.chips || []
            cond: tv.cond || ""
            img: tv.img || ""
            pending: tv.pending || false
            dim: tv.dim || false
            nameColor: tv.nameColor || ""
            decks: tv.decks || []
            draggable: page.draggable || (lib.isMain && lib.listsOpen)   // lists open: drag cards onto a list
            tileIndex: model.index
            selected: model.index === lib.currentRow
            selMode: lib.isMain && lib.sel.count > 0   // dimmed from the first chosen card on (the button alone dims nothing)
            picked: model.picked || false
            pickColor: lib.sel.accent ? "#ffa24a" : T.text   // (orange: the comparison picture for Oliver)
            width: grid.cellWidth
            height: grid.cellHeight
            appearDelay: Math.min(0.3, Math.max(0, model.index - grid.appearFirst) * 0.012)
            appearing: grid.appearGen > 0 && shell.animate
            // focus: fade image/text out or in radially, the chosen card flies (see focusState)
            readonly property var fz: page.fPhase > 0 ? page.focusState(tile, page.fu, x, y, grid.contentY) : null
            imgA: fz ? fz.img : 1
            txtA: fz ? fz.txt : 1
            fs: fz ? fz.s : 1
            fdx: fz ? fz.dx : 0
            fdy: fz ? fz.dy : 0
            fTop: page.fPhase > 0 && model.index === page.fFocus
            Connections {
                target: grid
                function onAppearGenChanged() { tile.appearing = false; tile.appearing = shell.animate }
            }
            // only while "Select" is on: a click chooses (Shift: a range) – otherwise it always opens the card (Oliver)
            choosing: lib.isMain && lib.sel.choosing
            onClicked: {
                if (lib.isMain && lib.sel.choosing)
                    lib.sel.click(model.index, tile.clickMods)
                else { page.reveal = model.index; lib.open(model.index) }
            }
            onDoubleClicked: page.tileDoubleClicked(model.index)
            onDragMoved: function (sx, sy) { page.dragMany = lib.sel.choosing && tile.picked ? lib.sel.count : 0
                                             page.tileDragMoved(model.index, tile.img, sx, sy) }
            onDragEnded: function (sx, sy) { page.tileDropped(model.index, sx, sy) }
        }

    }
    // lasso (review .106): a frame drawn on free space – between or below the cards – chooses everything under it
    // (Ctrl: adds to what is chosen). Lies over the grid; on a card it lets the press through (the card's own click,
    // drag). Worked out from the grid's cells, not per tile: smooth with 2000 cards. A click on free space clears the
    // choice. Only while "Select" is on (Oliver, after 0.9.3) – otherwise the grid gets every press itself.
    MouseArea {
        id: lasso
        z: 4
        enabled: lib.isMain && lib.sel.choosing
        x: grid.x; y: grid.y; width: grid.width; height: grid.height
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        property point p0          // in the grid's content (scrolls along)
        property point p1
        property bool on: false
        property bool add: false
        property string last: ""
        function onCard(cx, cy) {
            var i = grid.indexAt(cx, cy)
            if (i < 0) return false
            var lx = cx - (i % grid.cols) * grid.cellWidth, ly = cy - Math.floor(i / grid.cols) * grid.cellHeight
            return lx > 8 && lx < grid.cellWidth - 8 && ly > 6 && ly < grid.cellHeight - 6
        }
        onPressed: function (m) {
            var cx = m.x + grid.contentX, cy = m.y + grid.contentY
            if (onCard(cx, cy)) { m.accepted = false; return }
            p0 = Qt.point(cx, cy); p1 = p0; on = false; last = ""
            add = (m.modifiers & Qt.ControlModifier) !== 0
        }
        onPositionChanged: function (m) {
            // near the top/bottom edge: the grid scrolls along
            if (m.y > height - 30) grid.contentY = Math.max(0, Math.min(grid.contentHeight - grid.height, grid.contentY + 14))
            else if (m.y < 30) grid.contentY = Math.max(0, grid.contentY - 14)
            p1 = Qt.point(m.x + grid.contentX, m.y + grid.contentY)
            if (!on) {
                if (Math.abs(p1.x - p0.x) + Math.abs(p1.y - p0.y) < 6) return
                on = true
                lib.sel.lassoStart()
            }
            var c0 = Math.max(0, Math.floor(Math.min(p0.x, p1.x) / grid.cellWidth))
            var c1 = Math.min(grid.cols - 1, Math.floor(Math.max(p0.x, p1.x) / grid.cellWidth))
            var r0 = Math.max(0, Math.floor(Math.min(p0.y, p1.y) / grid.cellHeight))
            var r1 = Math.floor(Math.max(p0.y, p1.y) / grid.cellHeight)
            var sig = c0 + "," + c1 + "," + r0 + "," + r1
            if (sig === last) return   // the same cells: nothing to tell
            last = sig
            var out = []
            for (var r = r0; r <= r1; r++)
                for (var c = c0; c <= c1; c++) { var k = r * grid.cols + c; if (k < grid.count) out.push(k) }
            lib.sel.lasso(out, add)
        }
        onReleased: { if (!on && lib.sel.count > 0) lib.sel.none(); on = false }
        onCanceled: on = false
        Rectangle {   // the frame
            visible: lasso.on
            readonly property color ink: T.text
            x: Math.min(lasso.p0.x, lasso.p1.x) - grid.contentX; y: Math.min(lasso.p0.y, lasso.p1.y) - grid.contentY
            width: Math.abs(lasso.p1.x - lasso.p0.x); height: Math.abs(lasso.p1.y - lasso.p0.y)
            color: Qt.rgba(ink.r, ink.g, ink.b, 0.06)
            border.width: 1; border.color: Qt.rgba(ink.r, ink.g, ink.b, 0.6)
        }
    }
    // slim scrollbar: sits at the right edge of the grid – when detail/comparison comes in, their edge pushes it
    // ahead (and on closing it glides back with it); length and position glide softly to the new size
    Rectangle {
        id: sbar
        z: 3
        visible: grid.contentHeight > grid.height
        readonly property real panelLeft: compareView && compareView.visible ? compareView.x - 14 : (detailView.visible ? detailView.x - 16 : 1e9)
        x: Math.min(area.x + area.width, panelLeft) - 6; width: 5; radius: 2.5
        y: grid.y + grid.visibleArea.yPosition * grid.height
        height: Math.max(30, grid.visibleArea.heightRatio * grid.height)
        // on focus: from lift-off until the card lands (otherwise 0.32 s)
        readonly property real morphMs: page.fPhase > 0 ? (page.fPlan.fly[1] - page.fPlan.fly[0]) * fAnim.duration : 320
        // soft only when the grid re-lays out (focus, detail open/closed) – when scrolling the bar follows immediately
        // (previously it lagged behind the mouse wheel)
        Behavior on height { enabled: page.fPhase > 0 || area.morphing; NumberAnimation { duration: sbar.morphMs; easing.type: Easing.InOutQuad } }
        Behavior on y { enabled: page.fPhase > 0 || area.morphing; NumberAnimation { duration: sbar.morphMs; easing.type: Easing.InOutQuad } }
        color: sbGrab.containsMouse || sbGrab.pressed ? T.text2 : T.line2
        opacity: grid.moving || sbGrab.containsMouse || sbGrab.pressed ? 0.95 : 0.45
        MouseArea {   // grab and drag
            id: sbGrab
            anchors.fill: parent; anchors.margins: -6
            hoverEnabled: true; preventStealing: true; cursorShape: Qt.PointingHandCursor
            property real sy: 0
            property real sc: 0
            onPressed: function (m) { sy = mapToItem(grid, m.x, m.y).y; sc = grid.contentY }
            onPositionChanged: function (m) {
                if (!pressed) return
                var f = grid.contentHeight / Math.max(1, grid.height)
                grid.contentY = Math.max(grid.originY, Math.min(grid.originY + grid.contentHeight - grid.height,
                                                                sc + (mapToItem(grid, m.x, m.y).y - sy) * f))
            }
        }
        Behavior on opacity { NumberAnimation { duration: 300 } }
    }
    // re-lay the grid (detail/comparison/set progress open or closed, other card count), like morph.py used to:
    // remember previous places, jump to the end state at once, each card glides from its old to its new place
    // (own flight time by distance: near 0.12 s, across the screen 0.6 s; a touch of overshoot).
    // The chosen (otherwise the first visible) card stays in the same place if possible.
    function tiles() {
        var out = [], ch = grid.contentItem.children
        for (var i = 0; i < ch.length; i++)
            if (ch[i].tileIndex !== undefined && ch[i].tileIndex >= 0 && ch[i].visible) out.push(ch[i])
        return out
    }
    property int reveal: -1
    NumberAnimation { id: revealAnim; target: grid; property: "contentY"; duration: 420; easing.type: Easing.InOutCubic }
    function revealNow(i) {
        var it = grid.itemAtIndex(i)
        if (!it) return
        var top = grid.originY, bottom = grid.originY + Math.max(0, grid.contentHeight - grid.height), to = grid.contentY
        if (it.y < grid.contentY) to = it.y - 8
        else if (it.y + it.height > grid.contentY + grid.height) to = it.y + it.height - grid.height + 8
        to = Math.max(top, Math.min(bottom, to))
        if (Math.abs(to - grid.contentY) < 1) return
        revealAnim.stop(); revealAnim.from = grid.contentY; revealAnim.to = to; revealAnim.start()
    }
    function syncLayout() {
        var det = lib.detailOpen, cmp = lib.compareOpen, comp = lib.sideOpen, cols = Math.max(1, lib.columns)
        var rv = reveal; reveal = -1
        if (rv >= 0 && det === area.layDet && cmp === area.layCmp && comp === area.layComp && cols === grid.cols
                && fPhase === 0) revealNow(rv)
        if (fPhase > 0) {
            var w = fWant
            if (w && w.det === det && w.cmp === cmp && w.comp === comp && w.cols === cols) return   // already going there
            focusFinish()   // another change: finish the running one at once, then the new one
        }
        if (det === area.layDet && cmp === area.layCmp && comp === area.layComp && cols === grid.cols) {
            area.pDelay = 0; area.pDur = 460 * shell.speed
            area.visDet = det; area.visCmp = cmp; area.visComp = comp
            return
        }
        var anim = shell.animate && page.visible && grid.count > 0 && grid.width > 100
        var before = {}, anchor = -1, ts, i
        if (anim) {
            ts = tiles()
            for (i = 0; i < ts.length; i++) {
                var t = ts[i], vy = t.y - grid.contentY
                if (vy + t.height <= 0 || vy >= grid.height) continue
                var k = 1 - t.gk
                before[t.tileIndex] = {x: grid.x + t.x - grid.contentX + t.gx * k, y: vy + t.gy * k, w: t.width * t.gsc}
                if (anchor < 0 || t.tileIndex < anchor) anchor = t.tileIndex
            }
            var cur = lib.currentRow >= 0 ? lib.currentRow : page.lastSel   // closing: the last chosen one
            if (cur >= 0 && before[cur] !== undefined) anchor = cur
        }
        if (anim && anchor >= 0 && shell.animStyle === "focus") {
            focusStart({det: det, cmp: cmp, comp: comp, cols: cols}, before, anchor)
            return
        }
        area.pDelay = 0; area.pDur = 460 * shell.speed
        area.morphing = true; morphOff.restart()
        area.layDet = det; area.layCmp = cmp; area.layComp = comp; grid.cols = cols
        area.visDet = det; area.visCmp = cmp; area.visComp = comp
        if (!anim) return
        grid.forceLayout()
        if (anchor >= 0) {
            var a = grid.itemAtIndex(anchor)
            var ay = a ? a.y : Math.floor(anchor / grid.cols) * grid.cellHeight + grid.originY
            var top = grid.originY, bottom = grid.originY + Math.max(0, grid.contentHeight - grid.height)
            grid.contentY = Math.max(top, Math.min(bottom, ay - before[anchor].y))
            grid.forceLayout()
        }
        var across = Math.max(1, area.width)
        function ms(d) { return (120 + 480 * Math.pow(Math.min(1, d / across), 0.75)) * shell.speed }
        ts = tiles()
        for (i = 0; i < ts.length; i++) {
            var n = ts[i], nx = grid.x + n.x - grid.contentX, ny = n.y - grid.contentY
            if (ny + n.height <= 0 || ny >= grid.height) continue
            var b = before[n.tileIndex]
            if (b === undefined) { n.glideFrom(0, 24, 1, ms(0.25 * across), false, true); continue }
            var dx = b.x - nx, dy = b.y - ny
            var d = Math.sqrt(dx * dx + dy * dy) + Math.abs(b.w - n.width) * 2
            if (d < 0.5) continue
            n.glideFrom(dx, dy, b.w / n.width, ms(d), Math.abs(dy) > 4, false)
        }
    }
    // ---------- Focus (like morph.py used to, style „Focus“) ----------
    // 1) the other cards fade out radially with their text, the outermost first (closing: detail slides out)
    // 2) then the text of the chosen card – it stays the longest
    // 3) the chosen card is slowly lifted, flies in an arc (towards the centre) and is slowly put down
    // 4) the cards pop up radially, starting from it (opening: detail glides in meanwhile)
    // 5) shortly after: first the text of the chosen card, then that of the others radially
    readonly property var fPlans: ({
        "in": {out: [0.0, 0.24], own_out: [0.2, 0.3], fly: [0.3, 0.6], pop: [0.6, 0.9], own_in: [0.63, 0.73],
               text_in: [0.67, 1.0], pop_share: 0.5, panels: [0.6, 0.9]},
        "out": {out: [0.0, 0.36], own_out: [0.32, 0.42], fly: [0.42, 0.68], pop: [0.68, 0.97], own_in: [0.71, 0.8],
                text_in: [0.75, 1.0], pop_share: 0.62, panels: [0.0, 0.36]}})
    property int curRow: lib.currentRow
    property int lastSel: -1
    onCurRowChanged: if (curRow >= 0) lastSel = curRow
    Connections { target: lib; function onRefreshed(fresh) { if (fresh) page.lastSel = -1 } }
    Connections {   // a card picked from outside the grid (a list entry): scroll it into view
        target: lib
        function onSelectRow(i) { if (grid.itemAtIndex(i)) page.revealNow(i); else grid.positionViewAtIndex(i, GridView.Contain) }
    }
    property int fPhase: 0          // 0 off, 1 old grid (fade out), 2 new grid (flight, pop up)
    property real fu: 0
    property int fFocus: -1
    property var fPlan: fPlans["in"]
    property var fC: ({x: 0, y: 0})
    property real fFar: 1
    property var fFly: null
    property var fWant: null
    property string fMode: "in"
    property var fOrigin: ({})      // card -> scroll position before opening (closing: back exactly there)
    readonly property bool fFlying: fPhase > 0 && fu >= fPlan.fly[0] && fu <= fPlan.fly[1]
    NumberAnimation { id: fAnim; target: page; property: "fu"; from: 0; to: 1; easing.type: Easing.Linear
                      onFinished: page.focusFinish() }
    onFuChanged: if (fPhase === 1 && fu >= fPlan.fly[0]) focusApply()

    function sm(k) { k = Math.max(0, Math.min(1, k)); return k * k * (3 - 2 * k) }
    function stagger(u, span, d, share) {
        var dur = (span[1] - span[0]) * share, start = span[0] + d * (span[1] - span[0] - dur)
        return Math.max(0, Math.min(1, (u - start) / dur))
    }
    function outBack(k, s) { k -= 1; return k * k * ((s + 1) * k + s) + 1 }
    function inOutQuart(k) { return k < 0.5 ? 8 * k * k * k * k : 1 - Math.pow(-2 * k + 2, 4) / 2 }
    function focusState(t, u, tx, ty, cy0) {
        var cx = grid.x + tx - grid.contentX + t.width / 2, cy = ty - cy0 + t.height / 2
        var d = Math.min(1, Math.sqrt((cx - fC.x) * (cx - fC.x) + (cy - fC.y) * (cy - fC.y)) / fFar)
        var P = fPlan, k
        if (fPhase === 1) {
            if (t.tileIndex === fFocus)
                return {img: 1, txt: 1 - sm((u - P.own_out[0]) / (P.own_out[1] - P.own_out[0])), s: 1, dx: 0, dy: 0}
            k = sm(stagger(u, P.out, 1 - d, 0.6))
            return {img: 1 - k, txt: 1 - k, s: 1 - 0.1 * k, dx: 0, dy: 0}
        }
        if (t.tileIndex === fFocus && fFly) {
            var kf = Math.max(0, Math.min(1, (u - P.fly[0]) / (P.fly[1] - P.fly[0]))), e = inOutQuart(kf), F = fFly
            var x = (1 - e) * (1 - e) * F.x0 + 2 * (1 - e) * e * F.qx + e * e * F.x1
            var y = (1 - e) * (1 - e) * F.y0 + 2 * (1 - e) * e * F.qy + e * e * F.y1
            var sc = (F.w0 + (F.w1 - F.w0) * e) / F.w1 * (1 + 0.1 * Math.sin(Math.PI * kf))
            return {img: 1, txt: sm((u - P.own_in[0]) / (P.own_in[1] - P.own_in[0])), s: sc, dx: x - cx, dy: y - cy}
        }
        k = stagger(u, P.pop, d, P.pop_share)
        if (k <= 0) return {img: 0, txt: 0, s: 0.9, dx: 0, dy: 0}
        return {img: sm(k), txt: sm(stagger(u, P.text_in, d, 0.55)), s: 0.9 + 0.1 * outBack(k, 0.8), dx: 0, dy: 0}
    }
    function farFrom(c) {
        var far = 1, ts = tiles()
        for (var i = 0; i < ts.length; i++) {
            var t = ts[i], vy = t.y - grid.contentY
            if (vy + t.height <= 0 || vy >= grid.height) continue
            var x = grid.x + t.x - grid.contentX + t.width / 2, y = vy + t.height / 2
            far = Math.max(far, Math.sqrt((x - c.x) * (x - c.x) + (y - c.y) * (y - c.y)))
        }
        return far
    }
    function focusStart(want, before, anchor) {
        var appear = (want.det && !area.layDet) || (want.cmp && !area.layCmp) || (want.comp && !area.layComp)
        var gone = (!want.det && area.layDet) || (!want.cmp && area.layCmp) || (!want.comp && area.layComp)
        fMode = appear ? "in" : (gone ? "out" : "none")
        fPlan = fPlans[fMode === "in" ? "in" : "out"]
        var D = (shell.speed > 1 ? 460 : 1500) * Math.max(0.01, shell.speed)
        var b = before[anchor]
        fFocus = anchor
        fWant = want
        fFly = {x0: b.x + b.w / 2, y0: b.y + grid.cellHeight / 2, w0: b.w, startY: grid.contentY}
        fC = {x: fFly.x0, y: fFly.y0}
        fFar = farFrom(fC)
        // what disappears slides out right away (closing: while the cards fade out)
        area.pDelay = 0; area.pDur = (fPlan.panels[1] - fPlan.panels[0]) * D
        if (!want.det) area.visDet = false
        if (!want.cmp) area.visCmp = false
        if (!want.comp) area.visComp = false
        fu = 0
        fPhase = 1
        fAnim.duration = D
        fAnim.restart()
    }
    function focusApply() {   // middle: lay the new grid (all other cards are invisible right now)
        var want = fWant, D = fAnim.duration
        area.layDet = want.det; area.layCmp = want.cmp; area.layComp = want.comp; grid.cols = want.cols
        grid.forceLayout()
        var top = grid.originY, bottom = grid.originY + Math.max(0, grid.contentHeight - grid.height)
        var a = grid.itemAtIndex(fFocus)
        var ay = a ? a.y : Math.floor(fFocus / grid.cols) * grid.cellHeight + grid.originY
        if (fMode === "out" && fOrigin[fFocus] !== undefined) grid.contentY = Math.max(top, Math.min(bottom, fOrigin[fFocus]))
        else grid.contentY = Math.max(top, Math.min(bottom, ay + grid.cellHeight / 2 - grid.height / 2))   // centred
        if (fMode === "in" && want.det) { var o = {}; o[fFocus] = fFly.startY; fOrigin = o }
        grid.forceLayout()
        a = grid.itemAtIndex(fFocus)
        var x1 = grid.x + (a ? a.x : 0) - grid.contentX + grid.cellWidth / 2
        var y1 = (a ? a.y : ay) - grid.contentY + grid.cellHeight / 2
        // arc always towards the centre of the grid – never towards the screen edge
        var F = fFly, dx = x1 - F.x0, dy = y1 - F.y0, n = Math.sqrt(dx * dx + dy * dy) || 1
        var nx = -dy / n, ny = dx / n, mx = grid.x + grid.width / 2, my = grid.height / 2
        if (nx * (mx - (F.x0 + x1) / 2) + ny * (my - (F.y0 + y1) / 2) < 0) { nx = -nx; ny = -ny }
        fFly = {x0: F.x0, y0: F.y0, w0: F.w0, startY: F.startY, x1: x1, y1: y1, w1: grid.cellWidth,
                qx: (F.x0 + x1) / 2 + nx * 0.2 * n, qy: (F.y0 + y1) / 2 + ny * 0.2 * n}
        fC = {x: x1, y: y1}
        fFar = farFrom(fC)
        fPhase = 2
        // what gets added glides in during its time window (opening: while the cards pop up)
        area.pDelay = Math.max(0, (fPlan.panels[0] - fu) * D); area.pDur = (fPlan.panels[1] - fPlan.panels[0]) * D
        area.visDet = want.det; area.visCmp = want.cmp; area.visComp = want.comp
    }
    function focusFinish() {
        fAnim.stop()
        if (fPhase === 1) focusApply()
        fPhase = 0
        fFly = null
        area.pDelay = 0; area.pDur = 460 * shell.speed
    }

    Timer { id: layoutT; interval: 0; onTriggered: page.syncLayout() }
    Component.onCompleted: syncLayout()
    onVisibleChanged: { syncLayout(); if (!visible && lib.sel.active) lib.sel.end() }   // another page: choice ends
    Connections {
        target: lib
        function onChanged() { layoutT.restart() }
        function onSwapped() { detailView.skipSettle(); if (compareView) compareView.skipSettle() }   // nothing fades
        function onRefreshed(fresh) {
            if (fresh) {
                grid.positionViewAtBeginning()
                grid.appearFirst = 0
                grid.appearGen++
            } else {   // only newly shown (e.g. card added): stay in the same place
                var y = page.keepY
                Qt.callLater(function () {
                    grid.contentY = Math.max(grid.originY, Math.min(y, grid.originY + grid.contentHeight - grid.height))
                })
            }
        }
    }
    property real keepY: 0
    Connections {
        target: lib.model
        function onModelAboutToBeReset() { page.keepY = grid.contentY }
    }

    // alt arts still empty: a friendly sentence instead of an empty area
    Text {
        anchors.centerIn: grid
        visible: lib.isMain && lib.altOnly && grid.count === 0
        width: Math.min(560, grid.width * 0.8)
        text: shell.text("No alt-arts yet – the first ones will come from artists via the Scan Studio.")
        color: T.text2; font.family: T.font; font.pixelSize: 17
        wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
    }
    // empty collection: sentence + large buttons
    Column {
        anchors.centerIn: grid
        visible: lib.isMain && lib.emptyCollection && lib.mode === "mine" && grid.count === 0
        spacing: 18
        width: Math.min(640, grid.width * 0.8)
        Text {
            width: parent.width
            text: shell.text("This is where your collection lives. Scan your first cards – or bring a collection from ManaBox, Moxfield or a CSV file.")
            color: T.text2; font.family: T.font; font.pixelSize: 17
            wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 12
            Btn { text: shell.text("Scan cards"); primary: true; height: 46; width: 220; onClicked: lib.scanCards() }
            Btn { text: shell.text("Import collection …"); height: 46; width: 240; onClicked: lib.importCollection() }
        }
    }

    Rectangle { z: 4; x: 0; y: area.bottomY + 2; width: page.width; height: Math.max(0, page.height - y); color: T.bg }
    // ---------- Value history: expands above the status bar (click on the total value) ----------
    MouseArea {   // clicking beside it closes
        z: 17
        anchors.fill: parent
        visible: lib.valueOpen
        acceptedButtons: Qt.AllButtons
        onPressed: function (m) { lib.setValueOpen(false); m.accepted = false }
    }
    Rectangle {
        id: valuePanel
        z: 18
        x: page.pad; width: page.width - 2 * page.pad
        property real k: lib.valueOpen && lib.valueAvailable ? 1 : 0
        Behavior on k { NumberAnimation { duration: 240 * Math.max(0.01, shell.speed); easing.type: Easing.OutCubic } }
        readonly property real full: valueChart.implicitHeight
        height: full * k
        y: status.y - 8 - height
        visible: k > 0.01
        clip: true
        color: T.bg
        MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons; onWheel: function (w) { w.accepted = true } }
        ChartView {
            id: valueChart
            width: parent.width
            height: implicitHeight
            spec: lib.valueChart
            onActed: function (v) { if (v[0] === "link") lib.openStats() }   // „More statistics →“ next to the title
        }
        Btn {   // close – top right on the tile
            anchors.right: parent.right; anchors.rightMargin: 10; y: 10
            width: 32; height: 30; compact: true; glyph: "close"
            tip: shell.text("Close")
            onClicked: lib.setValueOpen(false)
        }
    }
    // ---------- Status bar ----------
    Row {
        id: status
        z: 5
        x: page.pad + 4
        anchors.bottom: parent.bottom; anchors.bottomMargin: 10
        spacing: 12
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: lib.status
            textFormat: Text.StyledText
            color: T.muted; font.family: T.font; font.pixelSize: 13
            linkColor: T.text   // total value (underlined): click expands the value history
            onLinkActivated: function (link) { if (link === "value") lib.toggleValue() }
            HoverHandler { cursorShape: parent.hoveredLink !== "" ? Qt.PointingHandCursor : Qt.ArrowCursor }
        }
        Btn {
            visible: !lib.hasDb
            text: shell.text("Load card database …")
            onClicked: lib.loadDb()
        }
    }

    Shortcut { sequence: "Ctrl+F"; enabled: page.visible; onActivated: search.focusAll() }
    Shortcut { sequence: "Escape"; enabled: page.visible && lib.isMain && lib.sel.active; onActivated: lib.sel.end() }
    Shortcut { sequence: "Escape"; enabled: page.visible && !(lib.isMain && lib.sel.active) && (lib.detailOpen || lib.compareOpen)
               onActivated: lib.escape() }
    Shortcut {   // everything shown (after search, filters, the Group-by node) – not while typing in a field
        sequence: "Ctrl+A"
        enabled: page.visible && lib.isMain && lib.sel.choosing && !(page.Window.activeFocusItem && typeof page.Window.activeFocusItem.cursorPosition === "number")
        onActivated: lib.sel.all()
    }
}
