// THE loading sign of the app (Oliver, 29.10.: one central piece – swap it here and it changes everywhere).
// Since 31.10.: a card is laid down, its folded corner swings back while the card straightens up, a glint runs over
// it, it sinks away and the next one comes – the first one is the Bent°Corner logo card (labs/loading-anim,
// draft d4 with Oliver's values). Drawn by a shader (shaders/loadcard.frag) whose time runs as a UniformAnimator on
// the render thread: it keeps moving while Python works on the GUI thread, and nothing ticks while it's hidden.
// Still picture of the logo card (−7°, flap folded over): animations off (Settings → Presentation) or still: true
// (tiny places like the scan tile); software rendering (no shaders): the same picture floating gently up and down.
// text: what is loading (optional, below); small: a compact version for inside a surface.
// leaving: loading is done and the surroundings are fading out anyway – the card sinks away meanwhile (the same 0.3 s
// as between two cards; never waited for).
import QtQuick

Item {
    id: ld
    property string text: ""
    property bool small: false
    property bool still: false
    property bool running: visible
    property bool leaving: false
    readonly property bool fx: GraphicsInfo.api !== GraphicsInfo.Software
    readonly property bool moving: running && !still && fx && (typeof shell === "undefined" || !shell || shell.animate)
    readonly property real k: small ? 0.42 : 1
    implicitWidth: Math.max(box.width + 120 * k, label.implicitWidth)
    implicitHeight: box.height + 14 * k + (label.text !== "" ? label.implicitHeight + 14 * k : 0)

    Item {   // the card's place in the layout (as big as the card); the drawing reaches beyond it
        id: box
        width: 108 * ld.k; height: 144 * ld.k
        anchors.horizontalCenter: parent.horizontalCenter
        y: 10 * ld.k

        ShaderEffect {
            id: fxv
            visible: ld.fx
            // the shader shows 130 units, the card is 70 of them high – as high as the old card (128)
            width: 128 * ld.k / 70 * 130; height: width
            anchors.centerIn: parent
            property real time: 0
            property real still: ld.moving ? 0 : 1
            property real dark: T.light ? 0 : 1
            property color cardColor: "#7c7c83"                     // hsl(240 3% 50%), in both looks (Oliver)
            property color tabColor: T.light ? "#8a8a8e" : "#5f5f63"   // back of the flap (Oliver: darker in the dark look)
            fragmentShader: "../shaders/loadcard.frag.qsb"
            property real leave: 0
            // the logo card first (brand/loadcard.json, ui/brand.py) – without brand/ all cards are random
            property vector4d loadCard: typeof brandInfo !== "undefined" ? Qt.vector4d(brandInfo.loadCard[0],
                brandInfo.loadCard[1], brandInfo.loadCard[2], brandInfo.loadCard[3]) : Qt.vector4d(0, 0, 0, 0)
            UniformAnimator {   // render thread; restarts with the logo card each time it starts
                target: fxv; uniform: "time"
                from: 0; to: 3600; duration: 3600 * 1000; loops: Animation.Infinite
                running: ld.moving
                onRunningChanged: if (running) fxv.leave = 0
            }
            UniformAnimator {   // done: sink away (GAP in the shader: 0.3 s)
                target: fxv; uniform: "leave"
                from: 0; to: 1; duration: 300
                running: ld.moving && ld.leaving
            }
        }
        Item {   // no shaders (software rendering): the logo card as a picture that floats gently up and down
            id: floater
            visible: !ld.fx
            width: parent.width; height: parent.height
            Image {
                id: still
                anchors.centerIn: parent
                width: 128 * ld.k / 70 * 100; height: width
                sourceSize: Qt.size(width * 2, height * 2)
                visible: typeof brandInfo !== "undefined" && brandInfo.logo
                source: visible ? Qt.resolvedUrl("../../brand/logo/loading-still-" + (T.light ? "auf-hell" : "auf-dunkel") + ".svg") : ""
            }
            Rectangle {   // without brand/: a plain card in the loading card's colour (neutral placeholder)
                visible: !still.visible
                anchors.centerIn: parent
                width: 128 * ld.k * 50 / 70; height: 128 * ld.k
                radius: width * 0.1
                color: "#7c7c83"
            }
            // ±4 % of the card height, 2.4 s per cycle – an Animator (render thread, also in the software backend);
            // animations off / still: a real still picture
            readonly property real amp: 128 * ld.k * 0.04
            SequentialAnimation {
                running: !ld.fx && ld.running && !ld.still && (typeof shell === "undefined" || !shell || shell.animate)
                loops: Animation.Infinite
                onStopped: floater.y = 0
                YAnimator { target: floater; from: 0; to: -floater.amp; duration: 600; easing.type: Easing.OutSine }
                YAnimator { target: floater; from: -floater.amp; to: floater.amp; duration: 1200; easing.type: Easing.InOutSine }
                YAnimator { target: floater; from: floater.amp; to: 0; duration: 600; easing.type: Easing.InSine }
            }
        }
    }
    Text {
        id: label
        anchors.horizontalCenter: parent.horizontalCenter
        y: box.y + box.height + 14 * ld.k
        text: ld.text
        visible: text !== ""
        color: T.muted; font.family: T.font; font.pixelSize: ld.small ? 12 : 13
    }
}
