// Soft edge instead of hard-clipped cards: place as a child in a ListView/GridView/Flickable – on the side
// where the content continues, a gradient in the background colour lies (becoming opaque towards the edge). So cards
// fade out gently instead of ending mid-frame. color = colour behind the scroll area.
import QtQuick

Item {
    id: e
    property Item target: null
    property color color: T.bg
    property real size: 34
    readonly property bool horiz: target !== null && target.contentWidth > target.width + 1
                                  && target.contentHeight <= target.height + 1
    readonly property real pos: !target ? 0 : horiz ? target.contentX - target.originX : target.contentY - target.originY
    readonly property real room: !target ? 0 : horiz ? target.contentWidth - target.width : target.contentHeight - target.height
    z: 49
    x: 0; y: 0; width: target ? target.width : 0; height: target ? target.height : 0
    Rectangle {   // start (left / top)
        visible: opacity > 0.01
        opacity: e.room > 1 ? Math.max(0, Math.min(1, e.pos / 24)) : 0
        x: 0; y: 0
        width: e.horiz ? e.size : e.width; height: e.horiz ? e.height : e.size
        gradient: Gradient {
            orientation: e.horiz ? Gradient.Horizontal : Gradient.Vertical
            GradientStop { position: 0; color: e.color }
            GradientStop { position: 1; color: Qt.rgba(e.color.r, e.color.g, e.color.b, 0) }
        }
    }
    Rectangle {   // end (right / bottom)
        visible: opacity > 0.01
        opacity: e.room > 1 ? Math.max(0, Math.min(1, (e.room - e.pos) / 24)) : 0
        x: e.horiz ? e.width - e.size : 0; y: e.horiz ? 0 : e.height - e.size
        width: e.horiz ? e.size : e.width; height: e.horiz ? e.height : e.size
        gradient: Gradient {
            orientation: e.horiz ? Gradient.Horizontal : Gradient.Vertical
            GradientStop { position: 0; color: Qt.rgba(e.color.r, e.color.g, e.color.b, 0) }
            GradientStop { position: 1; color: e.color }
        }
    }
    Component.onCompleted: {
        var f = parent
        while (f && f.visibleArea === undefined) f = f.parent
        if (f) { target = f; parent = f }   // like ScrollHint: on the scroll area itself, not on the content
    }
}
