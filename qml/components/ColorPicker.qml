// Colour picker in the program window: field (saturation × brightness), hue bar, presets, hex field, preview.
// cp: qfiles.ColorBackend.
import QtQuick

Item {
    id: root
    property var cp
    implicitHeight: 360
    implicitWidth: 620

    Rectangle {   // saturation (x) × brightness (y)
        id: sv
        width: 300; height: 300
        radius: 10
        color: Qt.hsva(root.cp.hue, 1, 1, 1)
        Rectangle {
            anchors.fill: parent; radius: 10
            gradient: Gradient { orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#ffffffff" }
                GradientStop { position: 1; color: "#00ffffff" } }
        }
        Rectangle {
            anchors.fill: parent; radius: 10
            gradient: Gradient {
                GradientStop { position: 0; color: "#00000000" }
                GradientStop { position: 1; color: "#ff000000" } }
        }
        Rectangle {
            width: 16; height: 16; radius: 8
            x: root.cp.sat * sv.width - 8; y: (1 - root.cp.val) * sv.height - 8
            color: "transparent"; border.width: 2; border.color: root.cp.val > 0.5 ? T.onHi : T.hi
        }
        function pick(px, py) { root.cp.setHsv(root.cp.hue, px / width, 1 - py / height) }
        TapHandler { onTapped: function (ev) { sv.pick(ev.position.x, ev.position.y) } }
        DragHandler { target: null
            onCentroidChanged: if (active) sv.pick(Math.max(0, Math.min(sv.width, centroid.position.x)), Math.max(0, Math.min(sv.height, centroid.position.y))) }
    }
    Rectangle {   // hue
        id: hue
        x: sv.width + 16; width: 26; height: 300; radius: 8
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#ff0000" }
                GradientStop { position: 0.17; color: "#ffff00" }
            GradientStop { position: 0.33; color: "#00ff00" }
                GradientStop { position: 0.5; color: "#00ffff" }
            GradientStop { position: 0.67; color: "#0000ff" }
                GradientStop { position: 0.83; color: "#ff00ff" }
            GradientStop { position: 1.0; color: "#ff0000" } }
        Rectangle { x: -3; width: parent.width + 6; height: 6; radius: 3; y: root.cp.hue * hue.height - 3
                    color: "transparent"; border.width: 2; border.color: T.hi }
        function pick(py) { root.cp.setHsv(Math.max(0, Math.min(1, py / height)), root.cp.sat, root.cp.val) }
        TapHandler { onTapped: function (ev) { hue.pick(ev.position.y) } }
        DragHandler { target: null; onCentroidChanged: if (active) hue.pick(centroid.position.y) }
    }
    Column {
        x: hue.x + hue.width + 24; width: root.width - x
        spacing: 12
        Rectangle { width: parent.width; height: 70; radius: 12; color: root.cp.hex; border.width: 1; border.color: T.line2 }
        Rectangle {
            width: parent.width; height: 38; radius: 10; color: T.surface; border.width: 1; border.color: hexIn.activeFocus ? T.line2 : T.line
            TextInput {
                id: hexIn
                x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter
                text: root.cp.hex; selectByMouse: true
                color: T.text; font.family: T.font; font.pixelSize: 15
                onEditingFinished: root.cp.setHex(text)
            }
        }
        Flow {
            width: parent.width; spacing: 6
            Repeater {
                model: root.cp.presets
                Rectangle { required property var modelData
                            width: 30; height: 30; radius: 8; color: modelData
                            border.width: root.cp.hex === modelData ? 2 : 1; border.color: root.cp.hex === modelData ? T.hi : T.line2
                            TapHandler { onTapped: root.cp.setHex(modelData) } }
            }
        }
        Row {
            spacing: 8
            Btn { height: 38; width: 120; text: shell.text("Cancel"); onClicked: root.cp.cancel() }
            Btn { height: 38; width: 120; primary: true; text: "OK"; onClicked: root.cp.accept() }
        }
    }
}
