// A light dropdown to switch and sort things (the look of the ☰ section menu in the detail view): lit = shown,
// dimmed = hidden (no ticks), a click switches; drag the grip to sort (the owner moves its things at the same time).
// Keyboard: ↑↓ choose, Space/Enter switch, Ctrl+↑↓ move, Esc closes. No veil – a click beside it closes.
//   openAt(key)   drops down right below key, its right edge on the key's right edge
//   model: [{text, shown, fixed}] (fixed = always shown: dimmed grip-less switch); toggled(i) / moved(from, to)
import QtQuick

Item {
    id: menu
    property string title: ""
    property var model: []
    property bool open: false
    property int dragFrom: -1
    property int dragTo: -1
    property real dragDy: 0
    property int cur: 0
    property rect key: Qt.rect(0, 0, 0, 0)
    signal toggled(int index)
    signal moved(int from, int to)
    function openAt(k) { owner = k; key = k.mapToItem(menu, 0, 0, k.width, k.height); cur = 0; open = true; mcard.forceActiveFocus() }
    // it lies on the window (above everything): it closes when the key that opened it goes (page switch) or a dialog
    // covers the window
    property Item owner: null
    readonly property bool gone: (!!owner && !owner.visible) || (!!Window.window && Window.window.covered === true)
    onGoneChanged: if (gone) open = false
    parent: Window.window ? Window.window.contentItem : null
    anchors.fill: parent
    z: 9990
    visible: opacity > 0.01
    opacity: open ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    // preventStealing / TakeOverForbidden (like MenuCard, c3048f5): a drag handler of the page below (a card tile, a
    // table row) must never take a press over – otherwise the first click into the menu does nothing
    MouseArea { anchors.fill: parent; enabled: menu.open; acceptedButtons: Qt.AllButtons; hoverEnabled: true
                preventStealing: true
                onPressed: menu.open = false; onWheel: function (w) { w.accepted = true } }
    Rectangle {
        id: mcard
        width: 300
        x: Math.max(8, Math.min(menu.width - width - 8, menu.key.x + menu.key.width - width))
        y: menu.key.y + menu.key.height + 4 + height <= menu.height - 8 ? menu.key.y + menu.key.height + 4
                                                                      : Math.max(8, menu.key.y - 4 - height)
        height: col.implicitHeight + ttl.height + 34 + foot.height + 8
        radius: Math.min(14, T.panelRadius)
        color: T.surface2
        border.width: 1; border.color: T.line2
        focus: menu.open
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; preventStealing: true }   // clicks stay in the menu
        function toggle(i) { var m = menu.model[i]; if (m && !m.fixed) menu.toggled(i) }
        function step(i, d) { var j = i + d; if (j < 0 || j >= menu.model.length) return; menu.moved(i, j); menu.cur = j }
        Keys.onUpPressed: function (ev) { if (ev.modifiers & Qt.ControlModifier) step(menu.cur, -1); else menu.cur = Math.max(0, menu.cur - 1) }
        Keys.onDownPressed: function (ev) { if (ev.modifiers & Qt.ControlModifier) step(menu.cur, 1); else menu.cur = Math.min(menu.model.length - 1, menu.cur + 1) }
        Keys.onSpacePressed: toggle(menu.cur)
        Keys.onReturnPressed: toggle(menu.cur)
        Keys.onEnterPressed: toggle(menu.cur)
        Keys.onEscapePressed: menu.open = false
        // how it works (Oliver: switching off wasn't recognizable): lit = shown, dimmed = hidden
        Text { id: foot; x: 14; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; width: parent.width - 28
               wrapMode: Text.Wrap; text: shell.text("Click = show/hide · drag the grip = sort")
               color: T.dim; font.family: T.font; font.pixelSize: 12 }
        Text { id: ttl; x: 14; y: 12; height: 28; verticalAlignment: Text.AlignVCenter; text: menu.title
               color: T.text2; font.family: T.font; font.pixelSize: 13; font.bold: true }
        Column {
            id: col
            x: 6; y: ttl.y + ttl.height + 6; width: parent.width - 12
            spacing: 2
            Repeater {
                id: rep
                model: menu.model
                delegate: Item {
                    id: r
                    required property var modelData
                    required property int index
                    width: col.width; height: 32
                    z: menu.dragFrom === index ? 5 : 0
                    readonly property real shift: menu.dragFrom < 0 ? 0 : index === menu.dragFrom ? menu.dragDy
                        : (index > menu.dragFrom && index <= menu.dragTo) ? -34
                        : (index < menu.dragFrom && index >= menu.dragTo) ? 34 : 0
                    property real shiftA: shift
                    Behavior on shiftA { enabled: menu.dragFrom !== r.index; NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                    transform: Translate { y: r.shiftA }
                    readonly property color ink: T.text   // T holds strings – as a color it has .r/.g/.b
                    Rectangle { anchors.fill: parent; radius: 8
                                color: menu.dragFrom === r.index ? T.button
                                       : menu.cur === r.index || rh.hovered ? Qt.rgba(r.ink.r, r.ink.g, r.ink.b, 0.08) : "transparent" }
                    HoverHandler { id: rh; onHoveredChanged: if (hovered) menu.cur = r.index }
                    Text { x: 34; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 44; elide: Text.ElideRight
                           text: r.modelData.text; color: T.text; font.family: T.font; font.pixelSize: 14
                           opacity: r.modelData.shown ? (r.modelData.fixed ? 0.75 : 1) : (rh.hovered || menu.cur === r.index ? 0.8 : 0.5) }
                    TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds; grabPermissions: PointerHandler.TakeOverForbidden
                                 onTapped: { menu.cur = r.index; mcard.toggle(r.index) } }
                    Item {   // grip
                        x: 4; anchors.verticalCenter: parent.verticalCenter
                        width: 24; height: 28
                        Column { anchors.centerIn: parent; spacing: 3
                                 Repeater { model: 2; Rectangle { width: 12; height: 1.6; radius: 0.8; color: mg.active || mh.hovered ? T.text : T.text2 } } }
                        HoverHandler { id: mh; cursorShape: mg.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor }
                        DragHandler {
                            id: mg
                            target: null; xAxis.enabled: false; dragThreshold: 3
                            onActiveChanged: {
                                if (active) { menu.dragFrom = r.index; menu.dragTo = r.index; menu.dragDy = 0 }
                                else {
                                    var from = menu.dragFrom, to = menu.dragTo
                                    menu.dragFrom = -1; menu.dragDy = 0
                                    if (from >= 0 && to !== from) { menu.moved(from, to); menu.cur = to }
                                }
                            }
                            onTranslationChanged: if (active) {
                                menu.dragDy = translation.y
                                menu.dragTo = Math.max(0, Math.min(rep.count - 1, r.index + Math.round(translation.y / 34)))
                            }
                        }
                    }
                }
            }
        }
    }
}
