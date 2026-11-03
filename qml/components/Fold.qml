// Collapsible section (like libview.Fold): a heading with a divider above it, no frame of its own (design rule: no
// boxes in boxes) – closed it is just the header, expanding grows the height softly with the content. Header: far left the grip for moving (two fine
// lines), then the arrow (rotates), title, grey extra (its own text, while closed). Fully clickable.
// Only expand/collapse animates the height – content arriving later (forms, prints …) sets it at once.
import QtQuick

Item {
    id: f
    property string title
    property string sub
    property string closedSub
    property bool open: true
    default property alias content: body.data
    property bool grippable: false     // grip on the left: move the section live
    property Component headerRight: null   // own element on the right of the header (e.g. „Non-Foil | Foil“)
    readonly property bool dragging: gd.active
    readonly property real headH: head.height
    signal toggled(bool on)
    signal gripStart()
    signal gripMove(real dy)
    signal gripEnd()
    width: parent ? parent.width : 300
    height: head.height + (open ? body.childrenRect.height + 14 : 0)   // no spacing between sections: the row is the header
    clip: true
    property bool animH: false
    onOpenChanged: { animH = true; animT.restart() }
    Timer { id: animT; interval: 380 * Math.max(1, shell.speed); onTriggered: f.animH = false }
    Behavior on height { enabled: shell.animate && f.animH; NumberAnimation { duration: 300 * shell.speed; easing.type: Easing.InOutCubic } }

    Rectangle {   // only while moving: a soft surface under the section being dragged
        anchors.fill: parent
        radius: 10
        color: Qt.lighter(T.surface, 1.12)
        visible: f.dragging
    }
    Rectangle { width: parent.width; height: 1; color: f.dragging ? T.line2 : T.line }   // divider above the heading

    Item {
        id: head
        width: parent.width
        height: 46   // divider to divider: hover surface and click cover the whole row, the content sits in its middle
        Rectangle { anchors.fill: parent; anchors.margins: 1; radius: 9
                    readonly property color ink: T.text   // T holds strings – as a color it has .r/.g/.b (light look: dark tint)
                    color: hh.hovered && !f.dragging ? Qt.rgba(ink.r, ink.g, ink.b, 0.04) : "transparent" }
        Item {   // grip: two fine lines; brighter when hovering the header, fully bright on the grip
            id: grip
            visible: f.grippable
            x: 4; anchors.verticalCenter: parent.verticalCenter
            width: 22; height: 30
            readonly property color ink: gd.active || gh.hovered ? T.text : (hh.hovered ? T.text2 : T.dim)
            Column {
                anchors.centerIn: parent
                spacing: 3
                Repeater { model: 2; Rectangle { width: 12; height: 1.6; radius: 0.8; color: grip.ink } }
            }
            HoverHandler { id: gh; cursorShape: gd.active ? Qt.ClosedHandCursor : Qt.OpenHandCursor }
            DragHandler {
                id: gd
                target: null; xAxis.enabled: false
                dragThreshold: 3
                onActiveChanged: if (active) f.gripStart(); else f.gripEnd()
                onTranslationChanged: if (active) f.gripMove(translation.y)
            }
        }
        Canvas {
            onAvailableChanged: if (available) requestPaint()   // preloaded pages: catch up on the first paint request
            id: arrow
            x: f.grippable ? 30 : 12; anchors.verticalCenter: parent.verticalCenter
            width: 12; height: 12
            rotation: f.open ? 90 : 0
            Behavior on rotation { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            onPaint: { var g = getContext("2d"); g.reset(); g.fillStyle = T.text2
                g.beginPath(); g.moveTo(3, 1.5); g.lineTo(10, 6); g.lineTo(3, 10.5); g.closePath(); g.fill() }
        }
        Text {
            id: ttl
            x: arrow.x + 20; anchors.verticalCenter: parent.verticalCenter
            text: f.title
            color: T.text; font.family: T.font; font.pixelSize: 15; font.bold: true
        }
        Loader {
            id: extra
            active: f.headerRight !== null
            sourceComponent: f.headerRight
            anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
        }
        Text {   // on the title's baseline (15 bold next to 12)
            anchors.left: ttl.right; anchors.leftMargin: 10
            anchors.right: extra.active ? extra.left : parent.right; anchors.rightMargin: extra.active ? 10 : 12
            anchors.baseline: ttl.baseline
            text: f.open ? f.sub : (f.closedSub || f.sub)
            color: T.muted; font.family: T.font; font.pixelSize: 12
            elide: Text.ElideRight
        }
        HoverHandler { id: hh; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: function (ev) {   // not if the own element on the right was clicked
                         if (extra.active && extra.item && ev.position.x >= extra.x - 4) return
                         f.toggled(!f.open) } }
    }
    Item {
        id: body
        y: head.height   // never under the header: there the (invisible) content would catch hover and clicks
        x: 12
        width: parent.width - 24
        height: childrenRect.height
        opacity: f.open ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
    }
}
