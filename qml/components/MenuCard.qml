// The light menu (one look for every menu and choice in the window): a narrow card with the title, the entries below,
// keyboard first – the focus sits on the current / first usable entry, ↑↓ move (separators, headings and greyed
// entries are skipped), Enter / → choose, ← / Esc go back. From 13 entries on, typing filters (Backspace deletes).
// Selection = brightness, no ticks: an entry with on: true is lit, on: false (or checkable and off) dimmed.
// items: [{text, enabled?, sep?, on?, sub?, desc?, indent?}] – an entry without key and enabled:false is a heading.
// multi: several at once – a click (or Space) switches an entry and the menu stays open; Enter, "Done" or Esc close and
// keep what was switched. Typing always filters then; freeText: when the filter matches nothing, Enter takes the
// typed text (takeText) – e.g. a set by name that has no code.
// Used by SheetLayer (Python menus, qdialogs.menu) and MenuSheet (ContextMenu, DropList).
import QtQuick

Rectangle {
    id: mc
    property string title: ""
    property var items: []
    property bool sub: false          // a submenu: "←" in the head
    property int start: -1            // entry with the focus at first (-1: the first usable one)
    property bool multi: false        // several at once (see above)
    property bool freeText: false     // multi: Enter on an empty filter result takes the typed text
    signal picked(int index)          // index into items (not the filtered list); multi: switched
    signal back()
    signal done()                     // multi: Enter / "Done" / Esc
    signal takeText(string text)      // freeText

    // multi: the switched state lives here (the items given in stay as they were)
    property var states: []
    onItemsChanged: { var s = []; for (var i = 0; i < items.length; i++) s.push(items[i].on === true); states = s }
    function isOn(i) { return multi ? states[i] === true : (items[i] || {}).on === true }
    function flip(i) {
        var s = states.slice(); s[i] = !s[i]; states = s
        mc.picked(i)
    }

    readonly property bool filterable: items.length > 12 || multi
    property string filter: ""
    readonly property var shown: {   // indices of the entries shown (filtering hides separators and headings)
        var out = [], f = filter.toLowerCase()
        for (var i = 0; i < items.length; i++) {
            var it = items[i]
            if (f && (it.sep || (it.text || "").toLowerCase().indexOf(f) < 0)) continue
            out.push(i)
        }
        return out
    }
    width: 340
    height: Math.min(maxHeight, head.height + (filterable ? 30 : 0) + list.contentHeight + 26)
    property real maxHeight: 600
    radius: Math.min(14, T.panelRadius)
    color: T.surface2
    border.width: 1; border.color: T.line2
    // clicks stay in the menu – preventStealing: a DragHandler of a card tile below must not take the press over
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; preventStealing: true }

    // where the card goes when it opens at a place (window coordinates of the parent): r = {x, y, w, h} – a click point
    // (w = h = 0: the card's corner at the point) or a key (the card below it, or above when the window ends there).
    // Only when there is no room it moves inwards / up – it always stays in the window. -> {x, y}
    function placeAt(r, W, H) {
        var m = 8, w = mc.width, h = mc.height
        var x = r.x + w <= W - m ? r.x : (r.w ? r.x + r.w - w : r.x - w)
        var below = r.y + r.h + (r.h ? 4 : 0)
        var y = below + h <= H - m ? below : (r.y - (r.h ? 4 : 0) - h >= m ? r.y - (r.h ? 4 : 0) - h : H - m - h)
        return {x: Math.max(m, Math.min(W - m - w, x)), y: Math.max(m, y)}
    }
    function usable(k) { var it = items[shown[k]]; return !!it && !it.sep && it.enabled !== false }
    function step(dlt) {
        var k = list.currentIndex
        for (var n = 0; n < shown.length; n++) {
            k = (k + dlt + shown.length) % shown.length
            if (usable(k)) { list.currentIndex = k; return }
        }
    }
    function choose() {
        if (multi) {
            if (freeText && filter && shown.length === 0) { mc.takeText(filter); filter = "" }
            else mc.done()
            return
        }
        if (usable(list.currentIndex)) mc.picked(shown[list.currentIndex])
    }
    function hit(i) { if (multi) flip(i); else mc.picked(i) }
    function focusFirst() {
        list.currentIndex = -1
        var at = mc.start >= 0 ? shown.indexOf(mc.start) : -1
        if (at >= 0 && usable(at)) list.currentIndex = at
        else step(1)
        list.positionViewAtIndex(Math.max(0, list.currentIndex), ListView.Contain)
        list.forceActiveFocus()
    }
    onFilterChanged: Qt.callLater(focusFirst)
    Component.onCompleted: focusFirst()

    Row {
        id: head
        x: 14; y: mc.title || mc.sub ? 12 : 2; height: mc.title || mc.sub ? 28 : 0
        visible: height > 0
        spacing: 10
        Btn { visible: mc.sub; text: "←"; height: 28; onClicked: mc.back() }
        Text { anchors.verticalCenter: parent.verticalCenter; text: mc.title
               width: mc.width - 28 - (mc.sub ? 48 : 0) - (mc.multi ? 86 : 0); elide: Text.ElideRight
               color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
    }
    Btn { visible: mc.multi; anchors.right: parent.right; anchors.rightMargin: 12; y: 10; height: 28
          text: shell.text("Done"); onClicked: mc.done() }
    Text {   // typing filters (long lists only)
        visible: mc.filterable
        x: 20; y: head.y + head.height + 4; width: mc.width - 40; height: 22
        text: !mc.filter ? shell.text("Type to filter")
              : mc.freeText && mc.shown.length === 0 ? "\u201e" + mc.filter + "\u201c " + shell.text("– Enter takes it")
              : mc.filter + "\u2502"
        color: mc.filter ? T.text : T.dim
        font.family: T.font; font.pixelSize: 12; elide: Text.ElideRight
    }
    ListView {
        id: list
        x: 6; y: head.y + head.height + 6 + (mc.filterable ? 26 : 0)
        width: mc.width - 12; height: mc.height - y - 8
        clip: true; interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        model: mc.shown
        focus: true
        highlightMoveDuration: 0
        Keys.onUpPressed: mc.step(-1)
        Keys.onDownPressed: mc.step(1)
        Keys.onReturnPressed: mc.choose()
        Keys.onEnterPressed: mc.choose()
        Keys.onRightPressed: if (mc.usable(currentIndex) && mc.items[mc.shown[currentIndex]].sub) mc.choose()
        Keys.onLeftPressed: if (mc.sub) mc.back()
        Keys.onEscapePressed: if (mc.filter) mc.filter = ""; else if (mc.multi) mc.done(); else mc.back()
        Keys.onSpacePressed: function (ev) {
            if (mc.multi && !mc.filter && mc.usable(currentIndex)) { mc.flip(mc.shown[currentIndex]); ev.accepted = true }
            else ev.accepted = false
        }
        Keys.onPressed: function (ev) {
            if (!mc.filterable) return
            if (ev.key === Qt.Key_Backspace) { mc.filter = mc.filter.slice(0, -1); ev.accepted = true }
            else if (ev.text && ev.text.length === 1 && ev.text >= " " && !(ev.modifiers & (Qt.ControlModifier | Qt.AltModifier))) {
                mc.filter += ev.text; ev.accepted = true
            }
        }
        delegate: Item {
            id: row
            required property var modelData   // index into mc.items
            required property int index
            readonly property var it: mc.items[modelData] || {}
            readonly property bool heading: it.enabled === false && it.key === undefined && !it.sep && !it.checkable
                                            && it.on === undefined && !it.sub && !!it.text && it.heading !== false
            readonly property bool usable: !it.sep && it.enabled !== false
            readonly property bool cur: ListView.isCurrentItem
            width: list.width
            height: it.sep ? 9 : it.desc ? 36 + ds.height : row.heading ? 26 : 34
            Rectangle { visible: row.it.sep === true; anchors.centerIn: parent; width: parent.width - 16; height: 1; color: T.line }
            Rectangle {   // hover / keyboard position
                visible: row.usable
                anchors.fill: parent; radius: 8
                readonly property color ink: T.text   // T holds strings – as a color it has .r/.g/.b
                color: row.cur || hov.hovered ? Qt.rgba(ink.r, ink.g, ink.b, 0.08) : "transparent"
            }
            HoverHandler { id: hov; enabled: row.usable; cursorShape: Qt.PointingHandCursor
                           onHoveredChanged: if (hovered) list.currentIndex = row.index }
            Text {
                id: tx
                visible: !row.it.sep
                x: 12 + (row.it.indent ? 14 : 0); y: row.it.desc ? 8 : (row.height - height) / 2
                width: parent.width - x - 12 - (row.it.sub ? 14 : 0)
                text: row.it.text || ""
                elide: Text.ElideRight
                font.family: T.font; font.pixelSize: row.heading ? 11 : 14; font.bold: row.heading
                font.capitalization: row.heading ? Font.AllUppercase : Font.MixedCase
                color: row.heading ? T.dim : T.text
                // selection = brightness: chosen / switched on = lit, the rest dimmed (no ticks)
                opacity: row.heading ? 1 : !row.usable ? 0.35
                         : mc.multi ? (mc.isOn(row.modelData) ? 1 : (hov.hovered || row.cur ? 0.85 : 0.55))
                         : (row.it.checkable || row.it.on === false) ? (hov.hovered || row.cur ? 0.85 : 0.55) : 1
            }
            Text {
                id: ds
                visible: !!row.it.desc
                x: tx.x; y: tx.y + tx.height + 2; width: tx.width
                text: row.it.desc || ""; wrapMode: Text.Wrap
                color: T.dim; font.family: T.font; font.pixelSize: 11
            }
            Text { visible: row.it.sub === true; anchors.right: parent.right; anchors.rightMargin: 12
                   anchors.verticalCenter: parent.verticalCenter; text: "›"
                   color: T.text2; font.family: T.font; font.pixelSize: 16 }
            MouseArea { anchors.fill: parent; enabled: row.usable; preventStealing: true; onClicked: mc.hit(row.modelData) }
        }
    }
}
