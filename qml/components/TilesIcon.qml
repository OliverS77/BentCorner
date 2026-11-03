// The tile drawer's sign (scan page): a big and a small tile, diagonal – not the screen. On hover the small tile
// slides up to the big one and back. Only Animators (render thread): it stays smooth while Python works on the GUI
// thread (the old canvas glint stuttered there – Oliver's review .101).
import QtQuick

Item {
    id: ti
    property color color: T.text2
    property bool play: false
    property real s: 1
    width: 18 * s; height: 18 * s
    Rectangle {   // the big tile, top left
        x: 0; y: 0; width: 11 * ti.s; height: 11 * ti.s; radius: 2.5 * ti.s
        color: "transparent"; border.width: 1.5; border.color: ti.color
    }
    Rectangle {   // the small one, bottom right
        id: small
        x: 11 * ti.s; y: 11 * ti.s; width: 7 * ti.s; height: 7 * ti.s; radius: 2 * ti.s
        color: "transparent"; border.width: 1.5; border.color: ti.color
    }
    SequentialAnimation {
        running: ti.play && (typeof shell === "undefined" || shell.animate)
        ParallelAnimation {
            XAnimator { target: small; from: 11 * ti.s; to: 8.5 * ti.s; duration: 220; easing.type: Easing.OutCubic }
            YAnimator { target: small; from: 11 * ti.s; to: 8.5 * ti.s; duration: 220; easing.type: Easing.OutCubic }
        }
        ParallelAnimation {
            XAnimator { target: small; from: 8.5 * ti.s; to: 11 * ti.s; duration: 260; easing.type: Easing.OutBack }
            YAnimator { target: small; from: 8.5 * ti.s; to: 11 * ti.s; duration: 260; easing.type: Easing.OutBack }
        }
    }
}
