// Move the data folder (separate process, while Bent°Corner is closed): text, progress, at the end possibly an
// error with „OK“. Logic: mover (setupui.MoverBackend).
import QtQuick
import QtQuick.Window
import "components"

Window {
    id: win
    width: 560; height: mover.error ? 260 : 170
    visible: false
    color: T.bg
    title: shell.text("Move data folder")

    property real runPos: 0   // indeterminate progress: bar runs back and forth
    SequentialAnimation on runPos {
        running: mover.total === 0 && mover.error === ""
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: 1; duration: 900; easing.type: Easing.InOutSine }
        NumberAnimation { from: 1; to: 0; duration: 900; easing.type: Easing.InOutSine }
    }

    Column {
        x: 28; y: 26; width: parent.width - 56
        spacing: 16
        Text { width: parent.width; wrapMode: Text.Wrap; text: mover.text
               color: T.text; font.family: T.font; font.pixelSize: 15 }
        Rectangle {
            visible: mover.error === ""
            width: parent.width; height: 8; radius: 4; color: T.button
            Rectangle {
                height: parent.height; radius: 4; color: T.text2
                width: mover.total > 0 ? parent.width * mover.done / mover.total : parent.width * 0.25
                x: mover.total > 0 ? 0 : win.runPos * (parent.width - width)
            }
        }
        Text { visible: mover.error !== ""; width: parent.width; wrapMode: Text.Wrap; text: mover.error
               color: "#ff8a8a"; font.family: T.font; font.pixelSize: 13 }
        Btn { visible: mover.error !== ""; text: "OK"; width: 100; height: 34; primary: true; onClicked: mover.ok() }
    }
}
