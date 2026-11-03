// Hint lamp on its own (orange, with a calm drop every 30 s) – like the dot on Btn, but independent of the
// button below (e.g. so it isn't greyed out along with a greyed-out button).
import QtQuick

Item {
    id: l
    width: 9; height: 9
    Rectangle {
        anchors.centerIn: parent
        width: 9; height: 9; radius: 4.5
        color: "transparent"; border.width: 1.5; border.color: "#ffa24a"
        opacity: 0
        SequentialAnimation on scale {
            running: l.visible && shell.animate; loops: Animation.Infinite
            PauseAnimation { duration: 2500 }
            NumberAnimation { from: 1; to: 3.2; duration: 1600; easing.type: Easing.OutCubic }
            PauseAnimation { duration: 27000 }
        }
        SequentialAnimation on opacity {
            running: l.visible && shell.animate; loops: Animation.Infinite
            PauseAnimation { duration: 2500 }
            NumberAnimation { from: 0.7; to: 0; duration: 1600; easing.type: Easing.OutCubic }
            PauseAnimation { duration: 27000 }
        }
    }
    Rectangle { anchors.fill: parent; radius: 4.5; color: "#ffa24a"; border.width: 2; border.color: Qt.rgba(0, 0, 0, 0.8) }
}
