// Orbit's Core: the quiet note IN PLACE of prices (Oliver/legal 06.11.) – part of the page, no pop-up: no dimming,
// it only takes clicks on its own area (the content under it is empty anyway). Exactly as big as what it stands for,
// so nothing moves. „Change level“ only opens Settings → Friends & privacy – the user moves the slider himself.
//   full: true  = a whole area (price alerts, detail prices, value charts): the sentence + the key
//   full: false = a narrow place (price column, value line, a deck's sum): one short key-like line „Prices from Near Orbit ›“
import QtQuick

Rectangle {
    id: v
    property bool full: true
    property string note: shell.text("Prices are available from Near Orbit on – nothing from your collection goes out.")
    visible: !shell.pricesOn
    color: full ? T.tile : "transparent"
    border.width: full ? 1 : 0; border.color: T.line
    radius: full ? 12 : 0
    implicitHeight: full ? Math.max(120, col.implicitHeight + 40) : 44
    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; hoverEnabled: true; preventStealing: true
                onWheel: function (w) { w.accepted = false } }   // the area is the veil's own – scrolling passes through
    Column {
        id: col
        visible: v.full && v.width >= 160   // a collapsed side bar: only the quiet area
        anchors.centerIn: parent
        width: Math.min(parent.width - 40, 520)
        spacing: 14
        Text { width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter
               text: v.note; color: T.text2; font.family: T.font; font.pixelSize: 14 }
        Btn { anchors.horizontalCenter: parent.horizontalCenter; height: 44; width: Math.max(180, implicitWidth)
              text: shell.text("Change level"); onClicked: shell.openOrbitSettings() }
    }
    Text {   // narrow places: the short line is the key itself (44 px tall area, grey, an arrow – no accent)
        id: short
        visible: !v.full
        anchors.verticalCenter: parent.verticalCenter
        x: 0; width: parent.width; elide: Text.ElideRight
        text: shell.text("Prices from Near Orbit") + "  ›"
        color: sma.containsMouse ? T.text : T.muted; font.family: T.font; font.pixelSize: 12
        MouseArea { id: sma; anchors.fill: parent; anchors.topMargin: -14; anchors.bottomMargin: -14
                    hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: shell.openOrbitSettings() }
    }
}
