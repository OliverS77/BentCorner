// Selection without a pop-up window: the button shows the current entry, a click opens the light menu (MenuSheet /
// MenuCard) right below the button like a dropdown (above it where the window ends; Esc or a click beside it closes,
// arrows + Enter, typing filters long lists). Selection = brightness: the current entry is lit, the others dimmed. items: [{key, text, desc?}] – desc =
// explanation below. title: the menu's heading (default: none).
// directional: the button has its own arrow toggle: ↓ = the normal sort order (name A–Z, price most expensive first
// …), ↑ = reversed. Clicking the arrow reverses without opening the menu; choosing another entry = ↓ (normal) first,
// choosing the current entry again reverses it.
// reversed is told by the button; reversing reports reverse().
import QtQuick

Item {
    id: d
    property var items: []
    property string current: ""
    property string title: ""
    property int minWidth: 180
    property int listWidth: 0          // (no longer used – the menu has its own width)
    property bool directional: false
    property string dir: "asc"
    property bool reversed: false   // directional: reversed (↑) instead of normal (↓)
    signal picked(string key)
    signal pickedDir(string key, string dir)
    signal reverse()

    readonly property string label: {
        for (var i = 0; i < items.length; i++) if (items[i].key === current) return items[i].text
        return ""
    }
    property bool open: false
    // as wide as the longest entry – the button doesn't jump when choosing, nothing is clipped
    FontMetrics { id: fm; font.family: T.font; font.pixelSize: 14; font.bold: true }
    readonly property real widest: {
        var w = 0
        for (var i = 0; i < items.length; i++) w = Math.max(w, fm.advanceWidth(items[i].text || ""))
        return w
    }
    implicitWidth: Math.max(minWidth, btn.implicitWidth, widest + 64 + (directional ? 28 : 0))
    implicitHeight: 36

    property real arrowAt: 0   // a tap on the direction arrow must not open the menu as well (the key gets it too)
    function show() {
        var ms = d.Window.window ? d.Window.window.menuSheet : null
        if (!ms || Date.now() - d.arrowAt < 400) return
        var its = d.items, menu = [], start = -1
        // a common lead-in like "Sortierung: " belongs on the key, not before every entry of the menu – only a
        // prefix that ends in ": " and that every entry has (never a common word: "Set A / Set B" stays as it is)
        var cut = 0
        if (its.length > 1) {
            var t0 = its[0].text || "", at = t0.indexOf(": ")
            if (at > 0) {
                var pre = t0.slice(0, at + 2)
                cut = pre.length
                for (var k = 1; k < its.length; k++) if ((its[k].text || "").indexOf(pre) !== 0) { cut = 0; break }
            }
        }
        for (var i = 0; i < its.length; i++) {
            menu.push({text: (its[i].text || "").slice(cut), desc: its[i].desc || "", on: its[i].key === d.current})
            if (its[i].key === d.current) start = i
        }
        d.open = true
        var r = btn.mapToItem(null, 0, 0, btn.width, btn.height)
        ms.open(d.title || (cut ? its[0].text.slice(0, cut - 2) : ""), menu, start, function (i) {
                    if (!its[i]) return
                    if (d.directional && its[i].key === d.current) d.reverse()   // the same sort again: the other way round
                    else d.picked(its[i].key)
                }, function () { d.open = false }, {at: {x: r.x, y: r.y, w: r.width, h: r.height}})
    }

    Btn {
        id: btn
        anchors.fill: parent
        text: d.label + (d.directional ? "      " : "   ▾")
        active: d.open
        marquee: true
        onClicked: d.show()
        function step(k) {
            for (var i = 0; i < d.items.length; i++) if (d.items[i].key === d.current) {
                var j = i + k
                if (j >= 0 && j < d.items.length) d.picked(d.items[j].key)
                return
            }
            if (d.items.length) d.picked(d.items[0].key)
        }
        Keys.onUpPressed: step(-1)
        Keys.onDownPressed: step(1)
        Rectangle {   // arrow on the button: its own toggle – reverse direction, the menu stays closed
            visible: d.directional
            // vertically centred on the visible key surface (the key's edge is at the bottom – so a bit higher)
            anchors.right: parent.right; anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -1.5
            width: 30; height: parent.height - 12; radius: 7
            color: dh.hovered ? Qt.rgba(1, 1, 1, 0.16) : Qt.rgba(1, 1, 1, 0.05)
            Text { anchors.centerIn: parent; text: d.reversed ? "↑" : "↓"; color: T.text
                   font.family: T.font; font.pixelSize: 16; font.bold: true }
            HoverHandler { id: dh; cursorShape: Qt.PointingHandCursor
                onHoveredChanged: if (hovered) { var p = parent.mapToItem(null, parent.width / 2, parent.height + 2)
                                                 shell.tip(shell.text("Reverse direction"), p.x, p.y) }
                                  else shell.tip("", 0, 0) }
            TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds
                         onTapped: {
                             d.arrowAt = Date.now()
                             var ms = d.Window.window ? d.Window.window.menuSheet : null
                             if (d.open && ms) ms.close()
                             d.reverse()
                         } }
        }
    }
}
