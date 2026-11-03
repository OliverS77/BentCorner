// Full-window loading screen (start while the pages preload, game switch, restore after minimising): the central
// loading sign (Loading.qml – the card deck being shuffled), below it the title and what is currently loading.
// It keeps moving while Python works (Loading uses only Animators); fading in/out also runs on the render thread.
import QtQuick

Rectangle {
    id: boot
    property int done: 0
    property int total: 1
    property bool finished: false
    readonly property string appName: typeof brandInfo !== "undefined" ? brandInfo.name : ""   // ui/brand.NAME
    property string title: appName
    property string sub: ""          // instead of „Loading … n / total“ (e.g. on game switch)
    property bool big: false         // game switch: name large, so you can see where it's going
    color: T.bg
    opacity: finished ? 0 : 1
    visible: !finished || opacity > 0.01   // (the OpacityAnimator writes opacity back only at its end)
    // fade in briskly, fade out softly (game switch: cover, switch, then calmly reveal)
    Behavior on opacity { OpacityAnimator { duration: boot.finished ? 520 : 300; easing.type: Easing.InOutCubic } }
    MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons }   // nothing passes through

    Loading {
        id: deck
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -44
        // the card's time starts once the screen has faded in (its own fade-in would otherwise go under in that of
        // the screen; the OpacityAnimator writes opacity back only at its end); while the screen fades out it sinks
        // away – within that fade, not a millisecond longer
        running: boot.visible && boot.opacity > 0.99
        leaving: boot.finished
    }
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: deck.y + deck.height + 30
        spacing: 8
        Lockup {   // the brand: the long version (card + BENT°CORNER) – a game's name stays text
            visible: boot.title === boot.appName
            anchors.horizontalCenter: parent.horizontalCenter
            size: boot.big ? 40 : 22; color: T.text }
        Text { visible: boot.title !== boot.appName
               anchors.horizontalCenter: parent.horizontalCenter; text: boot.title
               color: T.text; font.family: boot.big ? T.display : T.font; font.pixelSize: boot.big ? 40 : 22
               font.bold: true; font.letterSpacing: 1 }
        Text { anchors.horizontalCenter: parent.horizontalCenter
               text: boot.sub !== "" ? boot.sub
                                     : shell.text("Loading …") + "  " + Math.min(boot.done, boot.total) + " / " + boot.total
               color: boot.big ? T.text2 : T.muted; font.family: T.font; font.pixelSize: boot.big ? 18 : 13 }
    }
}
