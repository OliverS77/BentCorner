// Switch in the app's look (the user's rule "selection = brightness", no ticks): the small lamp like on the keys sits
// in a little slot and travels in it – left and dark when off, right and lit when on – so it reads as a switch (P3,
// Oliver: the bare lamp looked great but no one saw it could be switched). The text: off = dimmed, hover = almost
// normal, on = normal. The whole text is clickable.
import QtQuick

Item {
    id: c
    property string text
    property bool checked: false
    property string tip: ""
    property bool interactive: true   // false: display only (e.g. in a list row that toggles itself)
    signal toggled(bool on)
    implicitWidth: label.x + label.implicitWidth + 1   // the whole label in one line (incl. the lamp offset)
    implicitHeight: Math.max(22, label.implicitHeight)
    opacity: enabled ? 1 : 0.5
    property real lit: c.checked ? 1 : h.hovered && c.interactive ? 0.85 : 0.55
    Behavior on lit { NumberAnimation { duration: 140 } }

    Rectangle {   // the slot: sunk into the surface like the keys' wells, a little brighter edge under the mouse
        id: slot
        x: 0
        width: 28; height: 14; radius: 7   // (was 20×10 – Oliver: neither here nor there)
        anchors.verticalCenter: parent.verticalCenter
        color: T.keyDark
        border.width: 1; border.color: h.hovered && c.interactive ? T.line2 : T.line
        Rectangle {   // the lamp: off = grey on the left, on = lit on the right (with its glow)
            id: lamp
            x: c.checked ? slot.width - width - 3 : 3
            width: 8; height: 8; radius: 4
            anchors.verticalCenter: parent.verticalCenter
            color: c.checked ? T.hi : T.off
            Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
            Behavior on color { ColorAnimation { duration: 160 } }
            Rectangle {   // glow
                anchors.centerIn: parent; width: 16; height: 16; radius: 8
                color: T.hi; opacity: c.checked ? 0.18 : 0
                Behavior on opacity { NumberAnimation { duration: 160 } }
            }
        }
    }
    Text {
        id: label
        x: slot.width + 11
        width: Math.max(0, c.width - x)
        anchors.verticalCenter: parent.verticalCenter
        text: c.text
        color: T.text; font.family: T.font; font.pixelSize: 13
        opacity: c.lit
        wrapMode: Text.Wrap
    }
    activeFocusOnTab: enabled && interactive && visible
    Keys.onShortcutOverride: function (e) { if (e.key === Qt.Key_Space) e.accepted = true }
    Keys.onPressed: function (e) {
        if (e.key === Qt.Key_Space || e.key === Qt.Key_Return || e.key === Qt.Key_Enter) {
            e.accepted = true; c.checked = !c.checked; c.toggled(c.checked)
        }
    }
    Rectangle {   // focus ring around lamp and text
        visible: c.activeFocus
        x: -4; y: -3; width: Math.min(c.width, label.x + label.implicitWidth) + 8; height: c.height + 6; radius: 8   // around slot and text
        color: "transparent"; border.width: 1.5; border.color: T.hi; opacity: 0.8
    }
    HoverHandler { id: h; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: c.enabled && c.interactive; onTapped: { c.checked = !c.checked; c.toggled(c.checked) } }
    Timer { id: tipT; interval: 650; onTriggered: { var p = c.mapToItem(null, c.width / 2, c.height); shell.tip(c.tip, p.x, p.y) } }
    Connections { target: h; function onHoveredChanged() { if (h.hovered && c.tip !== "") tipT.restart(); else { tipT.stop(); shell.tip("", 0, 0) } } }
}
