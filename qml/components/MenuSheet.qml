// The light menu for QML's own menus and choices (ContextMenu, DropList): one per window (Main.qml: win.menuSheet).
// A clear surface over the page (no veil – menus don't darken) – a click on it or Esc closes –, the card (MenuCard) where it was opened: at the click
// point (context menus) or right at the key (choices); without a place in the upper middle.
// open(title, items, start, onPick, onClose, opts): onPick(index) after the menu has closed.
// opts.at {x, y, w, h}: the place in window coordinates – a point (w = h = 0) or the key that opened it.
// opts {multi: true, freeText: fn(text)}: several at once – onPick(index) on every switch (the menu stays open),
// onClose() when it closes (Enter, "Done", Esc, a click beside); freeText: the typed text when nothing matches.
import QtQuick

Item {
    id: ms
    anchors.fill: parent
    visible: opacity > 0.01
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    property bool shown: false
    property string title: ""
    property var items: []
    property int start: -1
    property var onPick: null
    property var onClose: null
    property bool multi: false
    property var onText: null
    property var at: null
    property int gen: 0   // a new MenuCard per opening (focus, filter and position start fresh)

    function open(title, items, start, onPick, onClose, opts) {
        if (ms.shown) close()
        ms.title = title || ""; ms.items = items || []; ms.start = start === undefined ? -1 : start
        ms.onPick = onPick || null; ms.onClose = onClose || null
        ms.multi = !!(opts && opts.multi); ms.onText = opts && opts.freeText ? opts.freeText : null
        var a = opts && opts.at ? ms.mapFromItem(null, opts.at.x, opts.at.y) : null
        ms.at = a ? {x: a.x, y: a.y, w: opts.at.w || 0, h: opts.at.h || 0} : null
        ms.gen++
        ms.shown = true
    }
    function close() {
        if (!ms.shown) return
        ms.shown = false
        var f = ms.onClose
        ms.onClose = null
        if (f) f()
    }
    function pick(i) {
        if (ms.multi) { if (ms.onPick) ms.onPick(i); return }
        var f = ms.onPick
        ms.onPick = null
        close()
        // after this click has been handled: the choice may open a dialog (its own event loop), and the card fades
        // out and is destroyed meanwhile – inside its handler Qt aborts the app (Oliver, review .101: „Umbenennen“)
        if (f) Qt.callLater(function () { f(i) })
    }

    Rectangle {   // clear surface: a click beside the menu closes it
        anchors.fill: parent
        color: "transparent"   // menus don't darken (only serious sheets do) – the clear surface still closes on a click beside
        MouseArea { anchors.fill: parent; enabled: ms.shown; acceptedButtons: Qt.AllButtons; hoverEnabled: true
                    preventStealing: true
                    onPressed: ms.close(); onWheel: function (w) { w.accepted = true } }
    }
    Loader {
        id: card
        active: ms.shown || ms.visible
        property int gen: ms.gen
        onGenChanged: { active = false; active = Qt.binding(function () { return ms.shown || ms.visible }) }
        readonly property var spot: item && ms.at ? item.placeAt(ms.at, ms.width, ms.height) : null
        x: spot ? spot.x : (ms.width - 340) / 2
        y: spot ? spot.y : Math.max(40, ms.height * 0.18)
        sourceComponent: MenuCard {
            title: ms.title
            items: ms.items
            start: ms.start
            maxHeight: ms.at ? ms.height - 16 : ms.height - card.y - 40
            enabled: ms.shown
            multi: ms.multi
            freeText: !!ms.onText
            onPicked: function (i) { ms.pick(i) }
            onBack: ms.close()
            onDone: ms.close()
            onTakeText: function (t) { if (ms.onText) ms.onText(t) }
        }
    }
}
