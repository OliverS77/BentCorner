// The strip ABOVE the mini game's field (lead 13.11.2026: as in the web – score and lives stay visible): "Done –
// everything is downloaded." · Keep playing · Let's go. Shown while game.stripOn (ScalperGame: done came while the
// game was open, only with canGo). Btn takes no focus on a click – the keyboard keeps playing.
// Two rows, a fixed height (library 13.11.: in the setup the field is only 240–280 px wide): the sentence on top over
// the full width (one line, … if it doesn't fit), the two keys centred below it.
import QtQuick

Rectangle {
    id: strip
    property Item game
    readonly property int pad: 8
    visible: !!game && game.stripOn
    height: visible ? pad + doneText.height + 6 + keys.height + pad : 0
    radius: 10
    color: Qt.rgba(0.07, 0.07, 0.08, 0.94); border.color: Qt.rgba(0.93, 0.93, 0.93, 0.25); border.width: 1
    Text {
        id: doneText
        x: strip.pad; y: strip.pad; width: strip.width - 2 * strip.pad
        horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; maximumLineCount: 1
        text: strip.game ? strip.game.doneText : ""; color: "#ededed"; font.family: T.font; font.pixelSize: 13
    }
    Row {
        id: keys
        anchors.horizontalCenter: parent.horizontalCenter
        y: doneText.y + doneText.height + 6; spacing: 8
        Btn { compact: true; text: strip.game ? strip.game.keepText : ""; onClicked: strip.game.keepPlaying() }
        Btn { compact: true; primary: true; text: strip.game ? strip.game.goText : ""
              onClicked: { strip.game.stripOn = false; strip.game.go() } }
    }
}
