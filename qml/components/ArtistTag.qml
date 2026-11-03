// Artist on image crops (Scryfall: if a crop is shown, name the artist in the same view) –
// small, bottom right in the image, as side info in chip style. name: artist, empty = invisible.
import QtQuick

Rectangle {
    id: tag
    property string name
    visible: name !== ""
    anchors.right: parent.right; anchors.bottom: parent.bottom
    anchors.rightMargin: 6; anchors.bottomMargin: 6
    width: label.implicitWidth + 12; height: 18; radius: 4
    color: Qt.rgba(0, 0, 0, 0.55)
    border.width: 1; border.color: Qt.rgba(1, 1, 1, 0.08)
    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, tag.parent ? tag.parent.width * 0.7 : 200)
        elide: Text.ElideRight
        text: "ILLUS. " + tag.name.toUpperCase()
        color: Qt.rgba(1, 1, 1, 0.62); font.family: T.font; font.pixelSize: 9; font.letterSpacing: 0.8
    }
}
