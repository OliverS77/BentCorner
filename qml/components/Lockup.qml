import QtQuick

// Bent°Corner long version (word-image mark, Oliver 30.10.2026 – labs/logo-2026-10-30/LIESMICH.md): card with dog-ear
// (no dot/ring – the ° is in the name), next to it BENT°CORNER in Barlow Semi Condensed SemiBold, one colour.
// Card 1.2 × font size, gap 0.16 em, card −0.12 em to the left, tracking 0.03 em. Same as ui/iconkit.lockup_image.
// The card is a brand asset (brand/, ui/brand.py): without it only the name.
Item {
    id: lock
    property real size: 24                 // font size (px)
    property color color: T.text
    readonly property bool onLight: (color.r + color.g + color.b) / 3 < 0.5   // dark ink = light background
    implicitWidth: word.x + word.implicitWidth
    implicitHeight: Math.max(card.visible ? card.height : 0, word.implicitHeight)
    width: implicitWidth; height: implicitHeight

    Image {
        id: card
        x: -0.12 * lock.size
        width: 1.2 * lock.size; height: width
        anchors.verticalCenter: parent.verticalCenter
        sourceSize: Qt.size(width * 2, height * 2)
        smooth: true
        visible: typeof brandInfo !== "undefined" && brandInfo.logo
        source: visible ? Qt.resolvedUrl("../../brand/logo/lockup-karte-" + (lock.onLight ? "auf-hell" : "auf-dunkel") + ".svg") : ""
    }
    Text {
        id: word
        x: card.visible ? card.x + card.width + 0.16 * lock.size : 0
        anchors.verticalCenter: parent.verticalCenter
        text: typeof brandInfo !== "undefined" ? brandInfo.word : ""   // ui/brand.WORD
        color: lock.color
        font.family: "Barlow Semi Condensed"
        font.weight: Font.DemiBold
        font.pixelSize: lock.size
        font.letterSpacing: 0.03 * lock.size
    }
}
