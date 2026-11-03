// Slim scroll bar (as in Settings). Simply put it as a child into a ListView/GridView/Flickable: attaches
// itself to the surrounding scroll area and only shows when its content is larger than the space – vertical
// or (for horizontal strips) horizontal at the bottom.
// The bar can be grabbed and dragged with the mouse (wider on hover). Vertically it also takes over the
// mouse wheel: one notch = a good distance, gliding smoothly (Ctrl+wheel stays free, e.g. for zoom).
import QtQuick

Rectangle {
    id: s
    property Item target: null
    property real wheelStep: 150        // pixels per notch
    readonly property bool horiz: target !== null && target.contentWidth > target.width + 1
                                  && target.contentHeight <= target.height + 1
    readonly property bool hot: grab.containsMouse || grab.pressed
    visible: target !== null && (horiz || target.contentHeight > target.height + 1)
    z: 50
    radius: (horiz ? height : width) / 2
    color: hot ? T.text2 : T.line2
    opacity: hot || (target && (target.moving || target.dragging)) ? 0.95 : 0.45
    Behavior on opacity { NumberAnimation { duration: 200 } }
    property real thick: hot ? 9 : 5
    Behavior on thick { NumberAnimation { duration: 120 } }
    x: !target ? 0 : horiz ? target.visibleArea.xPosition * target.width : target.width - width - 1
    y: !target ? 0 : horiz ? target.height - height - 1 : target.visibleArea.yPosition * target.height
    width: !target ? 0 : horiz ? Math.max(30, target.visibleArea.widthRatio * target.width) : thick
    height: !target ? 0 : horiz ? thick : Math.max(30, target.visibleArea.heightRatio * target.height)

    // ---- grab and drag ----
    MouseArea {
        id: grab
        anchors.fill: parent
        anchors.margins: -6            // a little more grip than visible
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        preventStealing: true
        property real startPos: 0
        property real startContent: 0
        onPressed: function (m) {
            var p = mapToItem(s.target, m.x, m.y)
            startPos = s.horiz ? p.x : p.y
            startContent = s.horiz ? s.target.contentX : s.target.contentY
            wheelAnim.stop()
        }
        onPositionChanged: function (m) {
            if (!pressed || !s.target) return
            var t = s.target, p = mapToItem(t, m.x, m.y)
            if (s.horiz) {
                var fx = t.contentWidth / Math.max(1, t.width)
                t.contentX = Math.max(t.originX, Math.min(t.originX + t.contentWidth - t.width, startContent + (p.x - startPos) * fx))
            } else {
                var fy = t.contentHeight / Math.max(1, t.height)
                t.contentY = Math.max(t.originY, Math.min(t.originY + t.contentHeight - t.height, startContent + (p.y - startPos) * fy))
            }
        }
    }

    // ---- mouse wheel: further and smooth ----
    NumberAnimation { id: wheelAnim; target: s.target; property: "contentY"; duration: 180; easing.type: Easing.OutCubic }
    function wheel(ev) {
        var t = s.target
        if (!t || s.horiz || (ev.modifiers & Qt.ControlModifier) || t.contentHeight <= t.height + 1) { ev.accepted = false; return }
        var d = ev.pixelDelta.y !== 0 ? ev.pixelDelta.y : ev.angleDelta.y / 120 * s.wheelStep
        if (d === 0) { ev.accepted = false; return }
        var lo = t.originY, hi = t.originY + t.contentHeight - t.height
        var base = wheelAnim.running ? wheelAnim.to : t.contentY
        var to = Math.max(lo, Math.min(hi, base - d))
        if (to === t.contentY && !wheelAnim.running) { ev.accepted = false; return }   // at the edge: pass on outwards
        wheelAnim.stop(); wheelAnim.from = t.contentY; wheelAnim.to = to; wheelAnim.start()
        ev.accepted = true
    }

    Component {
        id: wheelC
        WheelHandler { target: null; acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad }
    }
    Component.onCompleted: {
        // declared as a child it lands in the scrolling content – walk up to the scroll area and re-parent there
        var f = parent
        while (f && f.visibleArea === undefined) f = f.parent
        if (f) {
            target = f; parent = f
            // catch the mouse wheel over the whole scroll area (not just over the bar)
            var h = wheelC.createObject(f)   // finished component – don't recompile it for every bar
            h.wheel.connect(s.wheel)
            // only accept when there is something to scroll here – otherwise an inner area (e.g. the
            // pack list of the sessions, which doesn't scroll itself) snatched the wheel from the outer one
            h.enabled = Qt.binding(function () { return f.contentHeight > f.height + 1 && !s.horiz })
        }
    }
}
