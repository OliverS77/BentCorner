// Loading area: a light stripe runs evenly across at an angle – clearly shows „loading“ instead of pulsing
// (calm pulsing looked like a hung program). Sits on top of a placeholder: anchors.fill: parent.
import QtQuick

Item {
    id: s
    property bool running: visible
    property real strength: 0.09
    clip: true
    Rectangle {
        property real k: 0
        width: Math.max(40, s.width * 0.6); height: s.height * 2
        y: -s.height / 2
        x: -width * 1.3 + (s.width + width * 1.6) * k
        rotation: 18
        antialiasing: true
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Qt.rgba(1, 1, 1, 0) }
            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, s.strength) }
            GradientStop { position: 1; color: Qt.rgba(1, 1, 1, 0) }
        }
        SequentialAnimation on k {
            running: s.running && shell.animate   // performance level „Performance“: calm placeholder
            loops: Animation.Infinite
            NumberAnimation { from: 0; to: 1; duration: 1150; easing.type: Easing.InOutSine }
            PauseAnimation { duration: 200 }
        }
    }
}
