// Context menu in the window (no pop-up window): items [{text, key, sep?, enabled?, on?, indent?}], open(x, y) at a
// click point, openAt(key) at a key.
// x, y: the click point in this item's coordinates. Shown as the light menu (MenuSheet / MenuCard, one look for every
// menu): a narrow card at the click point (moved inwards only where the window ends), no veil, Esc or a click beside it closes, arrows + Enter; an entry with on: true/false shows by brightness.
// title: the card's heading (optional). picked(key) reports the choice; visible = open (e.g. for an active button).
import QtQuick

Item {
    id: m
    property var items: []
    property string title: ""
    signal picked(string key)
    visible: false
    function open(x, y, w, h) {
        var ms = m.Window.window ? m.Window.window.menuSheet : null
        if (!ms) return
        var its = m.items
        var p = m.mapToItem(null, x === undefined ? 0 : x, y === undefined ? 0 : y)
        visible = true
        ms.open(m.title, its, -1, function (i) {
            var it = its[i]
            if (it && it.key !== undefined) m.picked(it.key)
        }, function () { m.visible = false }, {at: x === undefined ? null : {x: p.x, y: p.y, w: w || 0, h: h || 0}})
    }
    // opened by a key: the card right at it (below, or above where the window ends)
    function openAt(key) {
        var r = key.mapToItem(null, 0, 0, key.width, key.height)
        var p = m.mapFromItem(null, r.x, r.y)
        open(p.x, p.y, r.width, r.height)
    }
    function close() {
        var ms = m.Window.window ? m.Window.window.menuSheet : null
        if (ms && visible) ms.close()
        visible = false
    }
}
