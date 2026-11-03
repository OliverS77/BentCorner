// „Coming soon“: Test (try decks alone – being rebuilt) and tabs the active game can't do yet (e.g. Decks in Pokémon).
import QtQuick

Item {
    id: page
    property string key
    Rectangle { anchors.fill: parent; color: T.bg }
    Column {
        anchors.centerIn: parent
        spacing: 14
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.pageTitle(page.key || "testing")
               color: T.text; font.family: T.display; font.pixelSize: 48 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: shell.text("Coming soon")
               color: T.muted; font.family: T.font; font.pixelSize: 18; font.letterSpacing: 3 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; visible: page.key === "testing" || page.key === ""
               text: shell.text("Try out decks: shuffle, draw, play – alone, against yourself")
               color: T.muted; font.family: T.font; font.pixelSize: 13 }
        Text { anchors.horizontalCenter: parent.horizontalCenter; visible: page.key !== "testing" && page.key !== ""
               text: shell.gameName(); color: T.muted; font.family: T.font; font.pixelSize: 13 }
    }
}
