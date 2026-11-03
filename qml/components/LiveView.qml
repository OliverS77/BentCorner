// Live image (qscan.LiveView): camera image as a texture (crop/zoom on the GPU), on top the drawing
// of the previous view (scan frame, lights, stream overlay) as an image. Mouse and wheel go to the previous logic.
import QtQuick

Item {
    id: root
    property var lv
    property bool active: visible
    onActiveChanged: if (lv) lv.setActive(active)
    Component.onCompleted: { if (lv) lv.setActive(active); report() }
    Component.onDestruction: if (lv) lv.setActive(false)
    onWidthChanged: report()
    onHeightChanged: report()
    function report() { if (lv && width > 0 && height > 0) lv.setSize(width, height, Screen.devicePixelRatio) }

    Rectangle { anchors.fill: parent; color: "black" }
    Item {   // camera image: only the visible crop (viewRect) fills the image area (canvas)
        id: cv
        x: root.lv ? root.lv.canvas.x : 0; y: root.lv ? root.lv.canvas.y : 0
        width: root.lv ? root.lv.canvas.width : 0; height: root.lv ? root.lv.canvas.height : 0
        clip: true
        readonly property real kx: root.lv && root.lv.viewRect.width > 0 ? width / root.lv.viewRect.width : 1
        readonly property real ky: root.lv && root.lv.viewRect.height > 0 ? height / root.lv.viewRect.height : 1
        Image {
            x: root.lv ? -root.lv.viewRect.x * cv.kx : 0
            y: root.lv ? -root.lv.viewRect.y * cv.ky : 0
            width: root.lv ? root.lv.frameSize.width * cv.kx : 0
            height: root.lv ? root.lv.frameSize.height * cv.ky : 0
            source: root.lv ? root.lv.camSource : ""
            visible: source !== ""
            cache: false
            asynchronous: false
            smooth: true
            mipmap: false
            fillMode: Image.Stretch
            retainWhileLoading: true
        }
    }
    Image {   // the camera rests: its last picture, blurred – fades out as soon as the live picture is back
        id: rest
        anchors.fill: parent
        source: root.lv ? root.lv.restSource : ""
        fillMode: Image.PreserveAspectCrop
        cache: false; smooth: true
        readonly property bool live: root.lv !== null && root.lv !== undefined && root.lv.camSource !== ""
        opacity: live ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 700; easing.type: Easing.OutCubic } }
        visible: source !== "" && opacity > 0.01
    }
    Image {   // drawing on top
        anchors.fill: parent
        source: root.lv ? root.lv.overlaySource : ""
        cache: false
        asynchronous: false
        smooth: false
        retainWhileLoading: true
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
        readonly property string cur: root.lv ? root.lv.cursor : "arrow"
        cursorShape: cur === "hand" ? Qt.PointingHandCursor : cur === "open" ? Qt.OpenHandCursor
                   : cur === "closed" ? Qt.ClosedHandCursor : cur === "move" ? Qt.SizeAllCursor : Qt.ArrowCursor
        // a click on the picture takes the focus: an open field (scan tiles) saves, like Enter
        onPressed: function (m) { forceActiveFocus(); root.lv.press(m.x, m.y, m.button) }
        onReleased: function (m) { root.lv.release(m.x, m.y, m.button) }
        onPositionChanged: function (m) { root.lv.move(m.x, m.y, m.buttons) }
        onDoubleClicked: function (m) { root.lv.doubleClick(m.x, m.y) }
        onEntered: root.lv.enter()
        onExited: root.lv.leave()
        onWheel: function (w) { root.lv.wheelMods(w.x, w.y, w.angleDelta.y, w.modifiers) }
    }
}
