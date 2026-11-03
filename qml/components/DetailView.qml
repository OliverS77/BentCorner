// Detail or comparison view (like libview.DetailPanel). det = qdetail.DetailBackend.
// Header stays at the top; below it the sections (card image, card text, prices, card, legality, print, rulings,
// all prints, IDs, in your collection, my lists, links) in the saved order – movable live via the 2×3-dot grip
// (right here or in the ☰ menu). The sections stay in place on updates (ListModel by key), otherwise
// e.g. the large card would be rebuilt on every little thing.
import QtQuick

Item {
    id: d
    property var det
    property bool holdCard: false   // view is gliding: the large card stands still with it, reflection only afterwards
    property bool hidePin: false    // side swap: Pin/⇄ – LibraryView crossfades by itself (old out, new in)
    signal swapRequested()          // ⇄ pressed (LibraryView first snapshots both views, then they are swapped)
    signal cardDragMoved(real sx, real sy)   // the big card dragged (window coordinates) – onto a list (Oliver, review .90)
    signal cardDropped(real sx, real sy)
    readonly property real pinX: head.x + btns.x + pinBtn.x
    readonly property real pinY: head.y + btns.y
    property bool imgReady: true
    // everything there (image, prints) – only then does the swap show the real views again instead of the snapshots
    readonly property bool ready: !det || !det.hasRow || (!det.printsLoading && imgReady)
    // New card: contents (forms, prints, prices …) arrive one after another. Meanwhile the sections below the image
    // stay invisible and then fade in together – instead of everything shifting down.
    property bool settling: false
    property real fade: 1           // opacity of the sections below the image
    readonly property int rowKey: det ? det.rowKey : 0
    onRowKeyChanged: { fadeIn.stop(); fade = 0; settling = true; settleT.restart(); settleMax.restart() }
    function settled() { settleT.stop(); settleMax.stop(); if (settling) { settling = false; fadeIn.restart() } }
    function skipSettle() { settleT.stop(); settleMax.stop(); settling = false; fadeIn.stop(); fade = 1 }
    Timer { id: settleT; interval: 220; onTriggered: d.settled() }
    Timer { id: settleMax; interval: 900; onTriggered: d.settled() }
    NumberAnimation { id: fadeIn; target: d; property: "fade"; to: 1; duration: 240; easing.type: Easing.OutCubic }
    clip: true
    Rectangle { anchors.fill: parent; z: -1; color: T.bg }   // opaque (glides over grid/comparison)

    // ---------- Header ----------
    Rectangle {
        id: head
        z: 5
        x: 4; y: 4
        width: d.width - 8
        height: 10 + 34 + 8 + 26 + 10   // two button rows with breathing room (the keys have shadows)
        radius: 12
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.lighter(T.surface, 1.12) }
            GradientStop { position: 1; color: T.surface }
        }
        border.width: 1; border.color: T.line
        visible: d.det.hasRow || d.det.isCompare
        HoverHandler { id: headHover }
        // row 1: name (scrolls through on hover if too long) | Pin, ☰, ✕
        Marquee {
            x: 14; y: 8
            width: parent.width - 14 - btns.width - 16; height: 36
            text: d.det.titleHtml + (d.det.altHtml ? "&nbsp;&nbsp;" + d.det.altHtml : "")
            format: Text.RichText
            px: 15
            running: headHover.hovered
        }
        // row 2: set across the full width | star, book right-aligned below the buttons
        Marquee {
            id: setM
            x: 14; y: 10 + 34 + 8
            width: parent.width - 14 - extras.width - 20; height: 26
            text: d.det.setLine
            format: Text.RichText
            px: 13
            running: headHover.hovered
        }
        Row {
            id: extras
            anchors.right: parent.right; anchors.rightMargin: 10
            y: setM.y
            spacing: 8
            Btn { id: star; compact: true; width: 30; height: 26; glyph: "lists"; inverted: d.det.star
                  tip: d.det.star ? shell.text("My lists: on a list – click: go to the section")
                                  : shell.text("My lists: wish, trade and own lists of this card")
                  onClicked: d.det.showLists() }
            Btn { id: bell; compact: true; width: 30; height: 26; glyph: "bell"; inverted: d.det.alarm
                  visible: d.det.canAlarm
                  tip: d.det.alarm ? shell.text("Price alert set – click: change (Orbit)")
                                   : shell.text("Price alert for this card (Orbit)")
                  onClicked: d.det.alarmForCard() }
            Btn { id: book; compact: true; width: 30; height: 26; glyph: d.det.rulings ? "book" : "bookEmpty"; opacity: d.det.rulings ? 1 : 0.5
                  tip: d.det.rulings ? shell.text("Additional rulings available – click: go to the rulings")
                                     : shell.text("No additional rulings for this card")
                  onClicked: d.det.showRulings() }
        }
        Row {
            id: btns
            anchors.right: parent.right; anchors.rightMargin: 10
            y: 10
            spacing: 8
            Btn { id: pinBtn; visible: d.det.canPin; width: 34; height: 34; compact: true
                  opacity: d.hidePin ? 0 : 1
                  glyph: d.det.isCompare ? "swap" : (d.det.pinned ? "pinOn" : "pin"); inverted: !d.det.isCompare && d.det.pinned
                  tip: d.det.isCompare ? shell.text("Swap sides: this card to the right, the other to the left")
                                       : shell.text("Pin: this card stays – the next one you click opens next to it")
                  onClicked: if (d.det.isCompare) d.swapRequested(); else d.det.setPinned(!d.det.pinned) }
            Btn { id: menuBtn; width: 34; height: 34; compact: true; glyph: "menu"; active: menu.open
                  tip: shell.text("Choose and sort sections"); onClicked: menu.open = !menu.open }
            Btn { visible: d.det.canClose; width: 34; height: 34; compact: true; glyph: "close"
                  tip: d.det.isCompare ? shell.text("Close comparison (Esc)") : shell.text("Close detail view (Esc)")
                  onClicked: d.det.close() }
        }
    }


    // ---------- Section menu ☰: the light menu (same look as every menu – MenuCard), with sorting ----------
    // A narrow card over the page, no veil (a click beside it or Esc closes). Shown sections are lit, hidden ones dimmed
    // (no ticks) – a click switches. Sorting: drag the grip, or with the keyboard ↑↓ choose, Space/Enter switches,
    // Ctrl+↑↓ moves the section. The card image stays at the top.
    Item {
        id: menu
        property bool open: false
        property int dragFrom: -1
        property int dragTo: -1
        property real dragDy: 0
        property int cur: 0
        property rect key: Qt.rect(0, 0, 0, 0)   // ☰ in window coordinates – the menu drops down right below it
        // it lies on the window (above everything): it closes when its detail view goes (page switch) or a dialog covers
        readonly property bool gone: !d.visible || (!!d.Window.window && d.Window.window.covered === true)
        onGoneChanged: if (gone) open = false
        parent: d.Window.window ? d.Window.window.contentItem : d
        anchors.fill: parent
        z: 9990
        visible: opacity > 0.01
        opacity: open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        onOpenChanged: if (open) {
            key = menuBtn.mapToItem(menu, 0, 0, menuBtn.width, menuBtn.height)
            cur = d.det.allFolds.length > 1 ? 1 : 0
            if (mLd.item) mLd.item.focusCard()
        }
        Loader {   // the content only while open or fading (there is one in every detail view)
            id: mLd
            anchors.fill: parent
            active: menu.open || menu.visible
            onLoaded: item.focusCard()
            sourceComponent: Item {
            function focusCard() { mcard.forceActiveFocus() }
            Rectangle {   // clear surface: a click beside the menu closes it
                anchors.fill: parent
                color: "transparent"   // menus don't darken (only serious sheets do) – the clear surface still closes on a click beside
                MouseArea { anchors.fill: parent; enabled: menu.open; acceptedButtons: Qt.AllButtons; hoverEnabled: true; preventStealing: true
                            onPressed: menu.open = false; onWheel: function (w) { w.accepted = true } }
            }
            Rectangle {
                id: mcard
                width: 340
                // a dropdown: right edge on the right edge of ☰, just below it (above if there is no room), in the window
                x: Math.max(8, Math.min(menu.width - width - 8, menu.key.x + menu.key.width - width))
                y: menu.key.y + menu.key.height + 4 + height <= menu.height - 8 ? menu.key.y + menu.key.height + 4
                                                                              : Math.max(8, menu.key.y - 4 - height)
                height: menuCol.implicitHeight + mtitle.height + 34 + mfoot.height + 8
                radius: Math.min(14, T.panelRadius)
                color: T.surface2
                border.width: 1; border.color: T.line2
                focus: menu.open
                MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; preventStealing: true }   // clicks stay in the menu
                function toggle(i) {   // the card image always stays
                    var f = d.det.allFolds[i]; if (f && f.key !== "image") d.applyMenu(i, !f.shown, 0)
                }
                function move(i, dlt) {   // the card image (index 0) stays at the top
                    var j = i + dlt
                    if (i < 1 || j < 1 || j >= d.det.allFolds.length) return
                    d.applyMenu(i, d.det.allFolds[i].shown, dlt)
                    menu.cur = j
                }
                Keys.onUpPressed: function (ev) {
                    if (ev.modifiers & Qt.ControlModifier) move(menu.cur, -1)
                    else menu.cur = Math.max(0, menu.cur - 1)
                }
                Keys.onDownPressed: function (ev) {
                    if (ev.modifiers & Qt.ControlModifier) move(menu.cur, 1)
                    else menu.cur = Math.min(d.det.allFolds.length - 1, menu.cur + 1)
                }
                Keys.onSpacePressed: toggle(menu.cur)
                Keys.onReturnPressed: toggle(menu.cur)
                Keys.onEnterPressed: toggle(menu.cur)
                Keys.onEscapePressed: menu.open = false
                // how it works (Oliver: switching off wasn't recognizable): lit = shown, dimmed = hidden
                Text { id: mfoot; x: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; width: parent.width - 28
                       wrapMode: Text.Wrap; text: shell.text("Click = show/hide · drag the grip = sort")
                       color: T.dim; font.family: T.font; font.pixelSize: 12 }
                Text {
                    id: mtitle
                    x: 14; y: 12; height: 28; verticalAlignment: Text.AlignVCenter
                    text: shell.text("Choose and sort sections")
                    color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true
                }
                Column {
                    id: menuCol
                    x: 6; y: mtitle.y + mtitle.height + 6; width: parent.width - 12
                    spacing: 2
                    Repeater {
                        id: menuRep
                        model: d.det.allFolds
                        delegate: Item {
                            id: mrow
                            required property var modelData
                            required property int index
                            width: menuCol.width; height: 32
                            z: menu.dragFrom === index ? 5 : 0
                            // while dragging: the dragged row follows the mouse, the others make room
                            readonly property real shift: menu.dragFrom < 0 ? 0 : index === menu.dragFrom ? menu.dragDy
                                : (index > menu.dragFrom && index <= menu.dragTo) ? -34
                                : (index < menu.dragFrom && index >= menu.dragTo) ? 34 : 0
                            property real shiftA: shift
                            Behavior on shiftA { enabled: menu.dragFrom !== mrow.index; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                            transform: Translate { y: mrow.shiftA }
                            Rectangle {   // hover / keyboard position / dragged
                                anchors.fill: parent; radius: 8
                                readonly property color ink: T.text   // T holds strings – as a color it has .r/.g/.b
                                color: menu.dragFrom === mrow.index ? T.button
                                       : menu.cur === mrow.index || rh.hovered ? Qt.rgba(ink.r, ink.g, ink.b, 0.08) : "transparent"
                            }
                            HoverHandler { id: rh; onHoveredChanged: if (hovered) menu.cur = mrow.index }
                            Text {   // shown = lit, hidden = dimmed (selection = brightness)
                                x: 34; anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - 44; elide: Text.ElideRight
                                text: mrow.modelData.title
                                color: T.text; font.family: T.font; font.pixelSize: 14
                                opacity: mrow.modelData.shown ? 1 : (rh.hovered || menu.cur === mrow.index ? 0.8 : 0.5)
                            }
                            TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; grabPermissions: PointerHandler.TakeOverForbidden   // the first click counts
                                         onTapped: { menu.cur = mrow.index; mcard.toggle(mrow.index) } }
                            Item {   // grip (far left, two fine lines like on the sections) – card image stays at the top
                                visible: mrow.modelData.key !== "image"
                                x: 4; anchors.verticalCenter: parent.verticalCenter
                                width: 24; height: 28
                                Column {
                                    anchors.centerIn: parent; spacing: 3
                                    Repeater { model: 2; Rectangle { width: 12; height: 1.6; radius: 0.8; color: mg.active || mh.hovered ? T.text : T.text2 } }
                                }
                                HoverHandler { id: mh; cursorShape: mg.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor }
                                DragHandler {
                                    id: mg
                                    target: null; xAxis.enabled: false; dragThreshold: 3
                                    onActiveChanged: {
                                        if (active) { menu.dragFrom = mrow.index; menu.dragTo = mrow.index; menu.dragDy = 0 }
                                        else {
                                            var from = menu.dragFrom, to = menu.dragTo
                                            menu.dragFrom = -1; menu.dragDy = 0
                                            if (from >= 0 && to !== from) { d.moveFold(from, to); menu.cur = to }
                                        }
                                    }
                                    onTranslationChanged: if (active) {
                                        menu.dragDy = translation.y
                                        menu.dragTo = Math.max(1, Math.min(menuRep.count - 1, mrow.index + Math.round(translation.y / 34)))
                                    }
                                }
                            }
                        }
                    }
                }
            }
            }
        }
    }
    function moveFold(from, to) {   // menu: row from to position to
        var all = det.allFolds, order = [], hidden = []
        for (var k = 0; k < all.length; k++) { order.push(all[k].key); if (!all[k].shown) hidden.push(all[k].key) }
        var key = order.splice(from, 1)[0]
        order.splice(to, 0, key)
        det.setLayout(order, hidden)
    }
    function applyMenu(i, shown, move) {
        var all = det.allFolds, order = [], hidden = []
        for (var k = 0; k < all.length; k++) order.push(all[k].key)
        if (move !== 0) { var j = i + move; var tmp = order[i]; order[i] = order[j]; order[j] = tmp }
        for (var m = 0; m < all.length; m++) {
            var key = all[m].key
            var on = m === i && move === 0 ? shown : all[m].shown
            if (!on) hidden.push(key)
        }
        det.setLayout(order, hidden)
    }

    // ---------- Content ----------
    Flickable {
        ScrollHint {}
        EdgeFade {}   // sections fade out softly at the top/bottom instead of being cut off hard
        id: flick
        anchors.fill: parent
        anchors.topMargin: head.visible ? head.height + 14 : 0
        contentHeight: body.height + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickDeceleration: 3500
        Column {
            id: body
            x: 6; width: flick.width - 18
            onHeightChanged: if (d.settling) settleT.restart()
            spacing: 0   // the sections bring their own air (Fold: 46 px header row, divider to divider)
            // glide only while dragging (otherwise everything follows expand/collapse directly – no lag)
            move: d.dragKey !== "" ? foldMove : null
            Transition { id: foldMove; NumberAnimation { properties: "y"; duration: 200; easing.type: Easing.OutCubic } }
            Text {   // without a card
                visible: !d.det.hasRow
                width: parent.width; height: 200
                text: d.det.isCompare ? "" : shell.text("Click a card on the left")
                color: T.muted; font.family: T.font; font.pixelSize: 15
                horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
            }
            Repeater {
                id: foldRep
                model: fm
                delegate: Fold {
                    id: fold
                    required property int index
                    required property string key
                    required property string fTitle
                    required property string fSub
                    required property string fClosedSub
                    required property bool fOpen
                    required property string html
                    required property bool chart
                    required property string boxes
                    width: body.width
                    title: fTitle; sub: fSub; closedSub: fClosedSub
                    open: fOpen
                    grippable: fm.count > 1 && fold.key !== "image"   // card image: always at the top, only collapsible
                    headerRight: fold.key === "image" ? cFinish : fold.key === "prints" ? cSameSet : null
                    onToggled: function (on) { d.det.setFold(fold.key, on) }
                    // drag: the section follows the mouse, the others slide (Column.move) out of the way
                    property real startY: 0
                    property real wantY: 0
                    z: dragging ? 10 : 0
                    opacity: fold.key !== "image" ? d.fade : 1
                    transform: Translate { y: fold.dragging ? fold.wantY - fold.y : 0 }
                    onGripStart: { d.dragKey = fold.key; d.dragItem = fold; startY = fold.y; wantY = fold.y }
                    onGripMove: function (dy) { wantY = startY + dy; d.dragCheck(fold) }
                    onGripEnd: d.dragDone()
                    Loader {
                        width: fold.width - 24
                        sourceComponent: fold.key === "image" ? cImage : fold.key === "prints" ? cPrints
                                       : fold.key === "own" ? cOwn : fold.key === "lists" ? cLists : cHtml
                        property var fd: ({key: fold.key, html: fold.html, chart: fold.chart, boxes: fold.boxes})
                    }
                }
            }
            Text {
                visible: d.det.note !== ""
                width: parent.width
                topPadding: 8
                text: d.det.note
                color: T.dim; font.family: T.font; font.pixelSize: 12
                wrapMode: Text.Wrap
            }
        }
    }
    // take over sections from Python without rebuilding existing ones (by key; order via move)
    ListModel { id: fm }
    property string dragKey: ""
    function syncFolds() {
        if (dragKey !== "") return   // don't interfere while dragging – the new state comes afterwards
        var fs = det.folds, i, j, k
        for (i = fm.count - 1; i >= 0; i--) {
            var keep = false
            for (j = 0; j < fs.length; j++) if (fs[j].key === fm.get(i).key) keep = true
            if (!keep) fm.remove(i)
        }
        for (k = 0; k < fs.length; k++) {
            var f = fs[k], at = -1
            for (j = 0; j < fm.count; j++) if (fm.get(j).key === f.key) at = j
            var props = {key: f.key, fTitle: f.title, fSub: f.sub, fClosedSub: f.closedSub, fOpen: f.open,
                         html: f.html || "", chart: f.chart === true, boxes: f.boxes || ""}
            if (at < 0) fm.insert(k, props)
            else {
                if (at !== k) fm.move(at, k, 1)
                for (var p in props) if (fm.get(k)[p] !== props[p]) fm.setProperty(k, p, props[p])
            }
        }
    }
    Connections { target: d.det; function onChanged() { d.syncFolds() } }
    Component.onCompleted: syncFolds()
    property var dragItem: null
    Timer {   // dragging at the top/bottom edge: keep scrolling softly (the section stays under the mouse)
        interval: 16; repeat: true
        running: d.dragItem !== null
        onTriggered: {
            var f = d.dragItem
            if (!f) return
            var vy = f.wantY - flick.contentY + f.headH / 2, edge = 56, v = 0
            if (vy < edge) v = -Math.min(1, (edge - vy) / edge) * 16
            else if (vy > flick.height - edge) v = Math.min(1, (vy - flick.height + edge) / edge) * 16
            if (v === 0) return
            var to = Math.max(0, Math.min(flick.contentHeight - flick.height, flick.contentY + v)), dv = to - flick.contentY
            if (Math.abs(dv) < 0.01) return
            flick.contentY = to
            f.startY += dv; f.wantY += dv
            d.dragCheck(f)
        }
    }
    function dragCheck(fold) {
        var i = fold.index, c = fold.wantY + fold.height / 2
        if (i > 0 && fm.get(i - 1).key !== "image") {   // never above the card image
            var a = foldRep.itemAt(i - 1)
            if (a && c < a.y + a.height / 2) { fm.move(i, i - 1, 1); return }
        }
        if (i < fm.count - 1) {
            var b = foldRep.itemAt(i + 1)
            if (b && c > b.y + b.height / 2) fm.move(i, i + 1, 1)
        }
    }
    function dragDone() {
        var vis = [], all = det.allFolds, order = [], hidden = [], i, vi = 0
        for (i = 0; i < fm.count; i++) vis.push(fm.get(i).key)
        for (i = 0; i < all.length; i++) {
            if (!all[i].shown) hidden.push(all[i].key)
            order.push(vis.indexOf(all[i].key) >= 0 ? vis[vi++] : all[i].key)
        }
        dragKey = ""
        dragItem = null
        det.setLayout(order, hidden)
    }

    Connections {
        target: d.det
        function onRevealRequested(key) {   // scroll to the section
            revealT.key = key; revealT.restart()
        }
    }
    Timer {
        id: revealT; property string key: ""; interval: 120
        onTriggered: {
            var folds = d.det.folds, y = 0
            for (var i = 0; i < body.children.length; i++) {
                var c = body.children[i]
                if (c.key !== undefined && c.key === key) { y = c.y; break }
            }
            scrollAnim.to = Math.max(0, Math.min(flick.contentHeight - flick.height, y - 8)); scrollAnim.restart()
        }
    }
    NumberAnimation { id: scrollAnim; target: flick; property: "contentY"; duration: 420; easing.type: Easing.InOutCubic }

    // „Non-Foil | Foil“ next to „Card image“ (display only: shimmer, prices, history, links – not saved);
    // if the print exists in only one finish, it says „Foil only“ or „Non-foil only“
    Component {
        id: cFinish
        Row {
            spacing: 6
            readonly property var fi: d.det.finishInfo || ({})
            visible: (fi.options || []).length > 0
            Repeater {   // Yu-Gi-Oh!: rarities of the same number to cycle through (UR | ScR | QCSR …)
                model: parent.fi.variants || []
                Row {
                    required property var modelData
                    required property int index
                    spacing: 6
                    Text { visible: index > 0; text: "|"; color: T.dim; font.family: T.font; font.pixelSize: 12 }
                    Text {
                        text: modelData.t
                        color: modelData.on || vh.hovered ? T.text : T.muted
                        font.family: T.font; font.pixelSize: 12; font.bold: modelData.on
                        MouseArea { id: vh; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
                                    property bool hovered: containsMouse
                                    cursorShape: Qt.PointingHandCursor
                                    onContainsMouseChanged: if (containsMouse) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 2)
                                                                                 shell.tip(modelData.tip, p.x, p.y) }
                                                            else shell.tip("", 0, 0)
                                    onClicked: { shell.tip("", 0, 0); if (!modelData.on) d.det.showVariant(modelData.sid) } }
                    }
                }
            }
            Repeater {
                model: (parent.fi.options || []).length > 1
                       ? [{"k": "n", "t": (parent.fi.labels || {}).n || "Non-Foil"}, {"k": "f", "t": (parent.fi.labels || {}).f || "Foil"}] : []
                Rectangle {   // unframed toggle (only the condition beside it is outlined): selected bright, else muted
                    required property var modelData
                    readonly property bool on: (modelData.k === "f") === (d.det.finishInfo.foil === true)
                    width: ft.implicitWidth + 10; height: 22; radius: 6; color: "transparent"
                    anchors.verticalCenter: parent.verticalCenter
                    border.width: 0
                    Text { id: ft; anchors.centerIn: parent; text: modelData.t
                           color: parent.on || fh.containsMouse ? T.text : T.muted
                           font.family: T.font; font.pixelSize: 12; font.bold: parent.on }
                    // MouseArea instead of TapHandler: in the section header the tap was otherwise cancelled
                    MouseArea { id: fh; anchors.fill: parent; hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: d.det.setFoilView(parent.modelData.k === "f") }
                }
            }
            Text {
                id: onlyT
                visible: (parent.fi.options || []).length === 1 && (parent.fi.variants || []).length === 0
                readonly property var fi: parent.fi
                text: ((fi.options || [])[0] === "foil" ? ((fi.labels || {}).f || "Foil")
                                                        : ((fi.labels || {}).n || "Non-foil")) + (fi.only === false ? "" : " only")
                color: T.muted; font.family: T.font; font.pixelSize: 12
                anchors.verticalCenter: parent.verticalCenter
                HoverHandler { id: oh
                    onHoveredChanged: if (hovered && onlyT.fi.tip) { var p = onlyT.mapToItem(null, onlyT.width / 2, onlyT.height + 2)
                                                                     shell.tip(onlyT.fi.tip, p.x, p.y) }
                                      else shell.tip("", 0, 0) }
            }
            Rectangle {   // condition: own copy or cards to add – click cycles through
                visible: d.det.condTag !== ""
                width: ct.implicitWidth + 16; height: 22; radius: 6; color: "transparent"
                anchors.verticalCenter: parent.verticalCenter
                border.width: 1.2; border.color: cm.containsMouse ? T.text : T.text2
                Text { id: ct; anchors.centerIn: parent; text: d.det.condTag
                       color: cm.containsMouse ? T.text : T.text2; font.family: T.font; font.pixelSize: 12; font.bold: true }
                MouseArea { id: cm; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onContainsMouseChanged: if (containsMouse) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 2)
                                                                          shell.tip(d.det.condTip, p.x, p.y) }
                                                    else shell.tip("", 0, 0)
                            onClicked: d.det.cycleCond() }
            }
        }
    }

    // ---------- Section contents ----------
    Component {
        id: cImage
        Column {
            spacing: 8
            BigCard {
                width: parent.width
                height: implicitHeight
                pic: d.det.imageGen + "|" + d.det.imageUrl
                mode: d.det.imageMode
                foil: d.det.foil || d.det.holo !== ""
                holo: d.det.holo
                held: d.holdCard
                onReadyChanged: d.imgReady = ready
                Component.onCompleted: d.imgReady = ready
                text: d.det.imageText
                loadingName: d.det.loadingName
                missing: d.det.imageMissing
                DragHandler {   // drag the card onto a list in the list column (the page shows the travelling card)
                    target: null; dragThreshold: 12
                    enabled: d.det.hasRow
                    onCentroidChanged: if (active) d.cardDragMoved(centroid.scenePosition.x, centroid.scenePosition.y)
                    onActiveChanged: if (!active) d.cardDropped(centroid.scenePosition.x, centroid.scenePosition.y)
                }
            }
            Item {
                width: parent.width; height: langFlow.height
                Flow {
                    id: langFlow
                    width: parent.width - (flipBtn.visible ? flipBtn.width + 8 : 0)
                    spacing: 6
                    Repeater {
                        model: d.det.langs
                        Btn { required property var modelData; compact: true; width: 56; height: 30
                              text: modelData.short; led: true; checkable: true; checked: modelData.current
                              tip: modelData.printed
                              onClicked: d.det.pickLang(modelData.code) }
                    }
                    Item {   // „Card image not available in this language“ – briefly, then gone again
                        id: lh
                        property bool on: false
                        height: 30; width: on ? lht.implicitWidth + 16 : 0; clip: true
                        Behavior on width { NumberAnimation { duration: 200 * shell.speed; easing.type: Easing.OutCubic } }
                        Text { id: lht; x: 8; anchors.verticalCenter: parent.verticalCenter; text: d.det.langHint
                               color: T.muted; font.family: T.font; font.pixelSize: 12 }
                        Timer { id: lhT; interval: 3000; onTriggered: lh.on = false }
                        Connections { target: d.det
                            function onChanged() { if (d.det.langHintRev !== lh.rev) { lh.rev = d.det.langHintRev
                                                   if (d.det.langHint !== "") { lh.on = true; lhT.restart() } } } }
                        property int rev: 0
                    }
                }
                Btn { id: flipBtn; visible: d.det.canFlip; anchors.right: parent.right; compact: true; width: 40; height: 30
                      text: "⟲"; active: d.det.flipped; tip: shell.text("Show back"); onClicked: d.det.flip() }
            }
            Text { visible: d.det.langNote !== ""; width: parent.width; text: d.det.langNote; color: T.muted
                   font.family: T.font; font.pixelSize: 12; wrapMode: Text.Wrap }
        }
    }
    Component {
        id: cHtml
        Column {
            spacing: 8
            Repeater {   // rules text per card face in a calm box
                model: fd.boxes ? fd.boxes.split("\u0001") : []
                Item {
                    required property string modelData
                    required property int index
                    width: parent.width
                    height: boxText.implicitHeight + (index > 0 ? 14 : 0)
                    Rectangle { visible: index > 0; width: parent.width; height: 1; color: T.line }
                    Text {
                        id: boxText
                        y: index > 0 ? 14 : 0; width: parent.width
                        text: modelData.replace(/<a /g, "<a style='color:" + color + "' ")   // links greyscale
                        textFormat: Text.RichText
                        wrapMode: Text.Wrap
                        color: T.text2; font.family: T.font; font.pixelSize: 13
                        onLinkActivated: function (link) { Qt.openUrlExternally(link) }
                    }
                }
            }
            Text {
                visible: fd.html !== ""
                width: parent.width
                text: fd.html.replace(/<a /g, "<a style='color:" + color + "' ")   // links greyscale, only underlined
                textFormat: Text.RichText
                wrapMode: Text.Wrap
                color: T.text2; font.family: T.font; font.pixelSize: 13
                // bc-artist:Name = search all cards by this artist (section „Print“), otherwise open the website
                onLinkActivated: function (link) {
                    if (link.indexOf("bc-artist:") === 0) d.det.searchArtist(decodeURIComponent(link.slice(10)))
                    else Qt.openUrlExternally(link)
                }
                HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
            }
            Text {   // legal 02.11.: where the shop links come from – exactly one of the two, once, small
                visible: fd.key === "prices" && d.det.shopNote !== ""   // only when a shop link is shown at the prices
                width: parent.width
                text: d.det.shopNote   // Scryfall's purchase_uris (Magic) – else our own links, no partner code
                wrapMode: Text.Wrap
                color: T.dim; font.family: T.font; font.pixelSize: 11
            }
            Loader {   // only in the „Prices“ section (otherwise the button would exist invisibly in every section)
                active: fd.key === "prices"
                visible: active && item !== null && item.links.length > 0
                width: parent.width
                sourceComponent: MarketLinks { width: parent ? parent.width : 300; links: d.det.shops }
            }
            // hint and chart only in the „Prices“ section: bound in every section, each change of the card computed the
            // whole price history ~10 times (d.det.chart, 40 calls per opening – survey 0.9.3.18)
            Loader {
                active: fd.key === "prices" && fd.chart !== true
                visible: active && (d.det.phHint.text || "") !== ""
                width: parent.width
                sourceComponent: PriceHint {
                    width: parent ? parent.width : 300
                    hint: d.det.phHint
                    onLoad: d.det.loadHistory()
                }
            }
            Loader {
                active: fd.chart === true
                visible: active
                width: parent.width
                sourceComponent: PriceChart {
                    width: parent ? parent.width : 300
                    info: d.det.chart
                    onFinishPicked: function (k) { d.det.setFinish(k) }
                    onRangePicked: function (days) { d.det.setRange(days) }
                }
            }
            Text {   // legal 02.11.: prices are estimates – once, small, at the end of the prices (under the chart, if any)
                visible: fd.key === "prices"
                width: parent.width
                text: shell.text("Prices are estimates from daily market data (Cardmarket, TCGplayer) – no guarantee. The shop has the final price.")
                wrapMode: Text.Wrap
                color: T.dim; font.family: T.font; font.pixelSize: 11
            }
        }
    }
    // „Same set“ next to „All prints“: on = only alternative prints from the card's set (selection = brightness)
    Component {
        id: cSameSet
        Text {
            text: shell.text("Same set")
            readonly property bool on: d.det.sameSet
            color: on ? T.text : (sh.containsMouse ? T.muted : T.dim)
            font.family: T.font; font.pixelSize: 12; font.bold: on
            MouseArea { id: sh; anchors.fill: parent; anchors.margins: -4; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: d.det.setSameSet(!d.det.sameSet) }
        }
    }
    Component {
        id: cPrints
        Column {
            Rectangle {   // still loading: full-height placeholder with a running light stripe
                visible: d.det.printsLoading
                width: parent.width; height: 212; radius: 10
                color: Qt.rgba(1, 1, 1, 0.03)
                Shimmer { anchors.fill: parent; running: d.det.printsLoading }
            }
            PrintStrip {
                fadeColor: T.surface
                visible: !d.det.printsLoading && d.det.prints.length > 1
                width: parent.width
                prints: d.det.prints
                onPicked: function (id) { d.det.pickPrint(id) }
            }
            Text { visible: !d.det.printsLoading && d.det.printsNote !== ""; text: d.det.printsNote; color: T.dim; font.family: T.font; font.pixelSize: 13 }
            Text { visible: !d.det.printsLoading && d.det.sameSet && d.det.prints.length <= 1
                   text: shell.text("No alternate prints in this set."); color: T.dim; font.family: T.font; font.pixelSize: 13 }
        }
    }
    Component { id: cOwn; Mirror { mirror: d.det.ownForm } }
    Component { id: cLists; MyLists { det: d.det } }
}
